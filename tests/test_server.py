"""Run: python -m unittest discover -s tests -p test_server.py -v.

The fake engine validates orchestration, failure semantics and process isolation;
it does not validate Folio translation quality. MCP is exercised over real stdio.
"""
import asyncio
from functools import partial
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

import pymupdf

from server.jobs import JobManager, ROOT, TERMINAL


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source with spaces.pdf"
        with pymupdf.open() as document:
            page = document.new_page()
            page.insert_text((50, 50), "A formula: E = mc2")
            document.save(self.source)
        self.engine = self.root / "fake-engine.py"
        self.engine.write_text("#!" + sys.executable + "\n" + '''
import json, pathlib, shutil, sys, time
request = json.load(sys.stdin)
folder = pathlib.Path(request['output_directory'])
folder.mkdir()
print(json.dumps({'type': 'progress', 'value': 0.2}), flush=True)
if request['fields'].get('test-mode') == 'slow': time.sleep(20)
if request['fields'].get('test-mode') == 'warnings':
    print(json.dumps({'type': 'notice', 'message': 'A refused paragraph retained its original text'}), flush=True)
    print(json.dumps({'type': 'problem', 'message': 'Temporary provider failure, retrying'}), flush=True)
    print(json.dumps({'type': 'progress', 'value': 0.8}), flush=True)
mono = folder / 'translated.pdf'
dual = folder / 'bilingual.pdf'
shutil.copyfile(request['input'], mono)
shutil.copyfile(request['input'], dual)
if request['fields'].get('test-mode') == 'failure':
    print(json.dumps({'type': 'failed', 'message': 'provider error ' + ''.join(request['secrets'].values())}), flush=True)
print(json.dumps({'type': 'finished', 'mono_pdf': str(mono), 'dual_pdf': str(dual)}), flush=True)
sys.exit(7 if request['fields'].get('test-mode') == 'failure' else 0)
''', encoding="utf-8")
        self.engine.chmod(0o755)
        self.manager = JobManager(self.root / "state", self.engine)
        self.manager.start = partial(self.manager.start, hover_highlight=False)

    def tearDown(self):
        self.manager.shutdown()
        self.temp.cleanup()

    def wait(self, job_id, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.manager.get(job_id)
            if status["state"] in TERMINAL:
                return status
            time.sleep(0.03)
        self.fail("Job did not terminate")

    def test_outputs_and_no_overwrite(self):
        original = self.source.read_bytes()
        first = self.manager.start(str(self.source), str(self.root / "output"))
        status = self.wait(first["job_id"])
        self.assertEqual(status["state"], "completed", status)
        self.assertEqual(set(status["artifacts"]), {"mono_pdf", "dual_pdf"})
        self.assertTrue(status["review_required"])
        second = self.manager.start(str(self.source), str(self.root / "output"))
        second_status = self.wait(second["job_id"])
        self.assertEqual(second_status["state"], "completed")
        self.assertNotEqual(status["output_directory"], second_status["output_directory"])
        self.assertEqual(self.source.read_bytes(), original)
        restarted = JobManager(self.root / "state", self.engine)
        self.assertEqual(restarted.get(first["job_id"])["state"], "completed")

    def test_failure_and_credential_redaction(self):
        secret = "test-secret-value-should-not-persist"
        os.environ["FOLIO_TEST_SECRET"] = secret
        try:
            first = self.manager.start(str(self.source), str(self.root / "output"), service="google", fields={"test-mode": "failure"},
                                       secret_env={"--api-key": "FOLIO_TEST_SECRET"})
            status = self.wait(first["job_id"])
        finally:
            del os.environ["FOLIO_TEST_SECRET"]
        self.assertEqual(status["state"], "failed")
        self.assertFalse(status["artifacts"])
        for path in [self.root / "state" / (first["job_id"] + ".json"),
                     Path(status["output_directory"]) / "engine.log"]:
            self.assertNotIn(secret, path.read_text())

    def test_cancellation_isolated_and_invalid_inputs(self):
        with self.assertRaises(ValueError):
            self.manager.start(str(self.source), str(self.root / "output"), pages="2")
        with self.assertRaises(ValueError):
            self.manager.get("../../state")
        slow = self.manager.start(str(self.source), str(self.root / "output"), service="google", fields={"test-mode": "slow"})
        fast = self.manager.start(str(self.source), str(self.root / "output"))
        self.manager.cancel(slow["job_id"])
        self.assertEqual(self.wait(slow["job_id"])["state"], "cancelled")
        self.assertEqual(self.wait(fast["job_id"])["state"], "completed")

    def test_selected_scanned_pages_are_rejected_and_warnings_persist(self):
        mixed = self.root / "mixed.pdf"
        with pymupdf.open(self.source) as document:
            picture = document[0].get_pixmap().tobytes("png")
            page = document.new_page()
            page.insert_image(page.rect, stream=picture)
            document.save(mixed)
        with self.assertRaisesRegex(ValueError, "pages: 2"):
            self.manager.start(str(mixed), str(self.root / "output"))
        job = self.manager.start(str(mixed), str(self.root / "output"), service="google", pages="1",
                                 fields={"test-mode": "warnings"})
        status = self.wait(job["job_id"])
        self.assertEqual(status["state"], "completed", status)
        self.assertEqual(status["last_event"]["type"], "progress")
        self.assertEqual([warning["type"] for warning in status["warnings"]], ["notice", "problem"])
        restarted = JobManager(self.root / "state", self.engine)
        self.assertEqual(restarted.get(job["job_id"])["warnings"], status["warnings"])

    def test_real_mcp_stdio(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        async def scenario():
            env = dict(os.environ, FOLIO_TRANSLATE_ENGINE=str(self.engine),
                       FOLIO_TRANSLATE_STATE_DIR=str(self.root / "mcp-state"))
            params = StdioServerParameters(command=sys.executable, args=["-m", "server", "serve"],
                                          cwd=str(ROOT), env=env)
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    self.assertEqual({tool.name for tool in tools.tools},
                                     {"start_translation", "get_pending_translations",
                                      "submit_translations", "get_translation_status", "cancel_translation"})
                    start_tool = next(tool for tool in tools.tools if tool.name == "start_translation")
                    self.assertNotIn("output_format", start_tool.inputSchema["properties"])
                    self.assertEqual(start_tool.inputSchema["properties"]["service"]["default"], "agent")
                    result = await session.call_tool("start_translation", {
                        "input_path": str(self.source), "output_directory": str(self.root / "mcp-output"), "hover_highlight": False})
                    self.assertFalse(result.isError, result)
                    status = result.structuredContent
                    self.assertIn("job_id", status)
                    for _ in range(100):
                        result = await session.call_tool("get_translation_status", {"job_id": status["job_id"]})
                        status = result.structuredContent
                        if status["state"] in TERMINAL:
                            break
                        await asyncio.sleep(0.03)
                    self.assertEqual(status["state"], "completed", status)
                    self.assertEqual(set(status["artifacts"]), {"mono_pdf", "dual_pdf"})
                    bad = await session.call_tool("get_translation_status", {"job_id": "../../outside"})
                    self.assertTrue(bad.isError)
        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
