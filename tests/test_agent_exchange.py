"""Check Agent translation exchange validation and local job orchestration.

The fake engine tests the exchange contract, not translation quality or the
native PDF engines. No network service or model credentials are used.
"""
import asyncio
from functools import partial
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

import pymupdf

from server.agent_exchange import pending_requests, submit_response
from server.jobs import JobManager, ROOT, TERMINAL


REQUEST_ID = "a" * 32
TRANSLATIONS = {"1": "质量矩阵为 {v1}。", "2": "保留原公式。"}


def envelope(request_id=REQUEST_ID):
    return {"version": 1, "request_id": request_id,
            "source_language": "en", "target_language": "zh",
            "instructions": "Translate prose and preserve formula placeholders exactly.",
            "context": "Mechanics paper, page 1.",
            "items": [{"id": "1", "source": "The mass matrix is {v1}.",
                       "kind": "paragraph", "is_short": False},
                      {"id": "2", "source": "Preserve the original formula.",
                       "kind": "paragraph", "is_short": False}]}


class AgentExchangeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "requests").mkdir()
        self.write_request()

    def tearDown(self):
        self.temp.cleanup()

    def write_request(self, request_id=REQUEST_ID):
        (self.root / "requests" / f"{request_id}.json").write_text(
            json.dumps(envelope(request_id)), encoding="utf-8")

    def test_pending_submission_and_idempotence(self):
        second_id = "b" * 32
        self.write_request(second_id)
        # Writers publish by atomic rename; incomplete temporary files stay hidden.
        (self.root / "requests" / "partial.tmp").write_text("{", encoding="utf-8")
        self.assertEqual(len(pending_requests(self.root)), 1)
        pending = pending_requests(self.root, limit=8)
        self.assertEqual({request["request_id"] for request in pending}, {REQUEST_ID, second_id})
        self.assertEqual(next(request for request in pending if request["request_id"] == REQUEST_ID),
                         envelope())
        result = submit_response(self.root, REQUEST_ID, TRANSLATIONS)
        self.assertEqual(result["request_id"], REQUEST_ID)
        self.assertEqual(result["state"], "submitted")
        response_path = self.root / "responses" / f"{REQUEST_ID}.json"
        response_bytes = response_path.read_bytes()
        self.assertEqual(json.loads(response_bytes),
                         {"version": 1, "request_id": REQUEST_ID, "translations": TRANSLATIONS})
        self.assertEqual([request["request_id"] for request in pending_requests(self.root, limit=8)],
                         [second_id])
        self.assertEqual(submit_response(self.root, REQUEST_ID, dict(TRANSLATIONS))["state"],
                         "already_submitted")
        with self.assertRaises(ValueError):
            submit_response(self.root, REQUEST_ID, {**TRANSLATIONS, "2": "不同的译文。"})
        self.assertEqual(response_path.read_bytes(), response_bytes, "Never overwrite a submitted reply")

    def test_invalid_translations_and_request_ids_do_not_publish(self):
        invalid = [
            {"1": TRANSLATIONS["1"]},
            {**TRANSLATIONS, "3": "多余的条目。"},
            {**TRANSLATIONS, "1": "  \n\t"},
            {**TRANSLATIONS, "1": 123},
            {**TRANSLATIONS, "1": None},
            {**TRANSLATIONS, "1": "质量矩阵。"},
            {**TRANSLATIONS, "1": "质量矩阵 {v1} {v1}。"},
            {**TRANSLATIONS, "1": "质量矩阵 {v2}。"},
        ]
        for translations in invalid:
            with self.subTest(translations=translations), self.assertRaises(ValueError):
                submit_response(self.root, REQUEST_ID, translations)
            self.assertFalse((self.root / "responses" / f"{REQUEST_ID}.json").exists())
        for request_id in ("../outside", "", "a" * 31, "a" * 33, "/tmp/" + REQUEST_ID):
            with self.subTest(request_id=request_id), self.assertRaises(ValueError):
                submit_response(self.root, request_id, TRANSLATIONS)
        with self.assertRaises((ValueError, FileNotFoundError)):
            submit_response(self.root, "c" * 32, TRANSLATIONS)
        self.assertEqual([request["request_id"] for request in pending_requests(self.root)], [REQUEST_ID])

    def test_sentence_mode_preserves_pairs_and_reassembles_native_response(self):
        request = envelope()
        request['items'] = [{'id': '1', 'source': 'See Fig. {v1}. It costs 3.6 s. Continue {v0} here.',
                             'kind': 'paragraph', 'is_short': False}]
        (self.root / 'requests' / f'{REQUEST_ID}.json').write_text(json.dumps(request))
        (self.root / 'sentence-mode').touch()
        items = pending_requests(self.root)[0]['items']
        self.assertEqual([i['source'] for i in items], ['See Fig. {v1}.', 'It costs 3.6 s.', 'Continue {v0} here.'])
        values = ['见图 {v1}。', '耗时 3.6 秒。', '在此 {v0} 继续。']
        translated = {i['id']: t for i, t in zip(items, values)}
        with self.assertRaises(ValueError):
            submit_response(self.root, REQUEST_ID, {**translated, items[0]['id']: '见图。'})
        self.assertFalse((self.root / 'alignments').exists())
        submit_response(self.root, REQUEST_ID, translated)
        native = json.loads((self.root / 'responses' / f'{REQUEST_ID}.json').read_text())
        self.assertEqual(native['translations'], {'1': ' '.join(values)})
        alignment = json.loads((self.root / 'alignments' / f'{REQUEST_ID}.json').read_text())
        self.assertEqual(alignment['items'][0]['sentences'],
                         [{'source': i['source'], 'translation': t} for i, t in zip(items, values)])
        self.assertEqual(submit_response(self.root, REQUEST_ID, translated)['state'], 'already_submitted')

    def test_concurrent_process_submissions_never_overwrite(self):
        worker = r'''
from contextlib import contextmanager
import json, pathlib, sys, time
from server import agent_exchange
root, request_id, gate_path, participant, payload = sys.argv[1:]
gate = pathlib.Path(gate_path)
translations = json.loads(payload)
original_temporary_file = agent_exchange.tempfile.NamedTemporaryFile
@contextmanager
def simultaneous_publish(*args, **kwargs):
    with original_temporary_file(*args, **kwargs) as stream:
        yield stream
    # Both processes must finish their complete temporary response before either
    # publishes. This exposes the former exists()+replace() overwrite race.
    (gate / participant).write_text('ready', encoding='utf-8')
    deadline = time.monotonic() + 5
    while len(list(gate.iterdir())) != 2:
        if time.monotonic() > deadline:
            raise TimeoutError('Other submitter did not reach the publication barrier')
        time.sleep(0.005)
agent_exchange.tempfile.NamedTemporaryFile = simultaneous_publish
try:
    result = agent_exchange.submit_response(pathlib.Path(root), request_id, translations)
except ValueError:
    result = {'request_id': request_id, 'state': 'conflict'}
print(json.dumps(result), flush=True)
'''
        for same_response, request_id in ((False, "d" * 32), (True, "e" * 32)):
            with self.subTest(same_response=same_response):
                self.write_request(request_id)
                gate = self.root / ("race-" + request_id)
                gate.mkdir()
                replies = [dict(TRANSLATIONS), dict(TRANSLATIONS)]
                if not same_response:
                    replies[1]["2"] = "第二个进程提交的不同译文。"
                processes = [subprocess.Popen(
                    [sys.executable, "-c", worker, str(self.root), request_id, str(gate),
                     str(index), json.dumps(reply)], cwd=ROOT,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    for index, reply in enumerate(replies)]
                try:
                    results = []
                    for process in processes:
                        stdout, stderr = process.communicate(timeout=10)
                        self.assertEqual(process.returncode, 0, stdout + stderr)
                        results.append(json.loads(stdout))
                finally:
                    for process in processes:
                        if process.poll() is None:
                            process.kill()
                            process.communicate()
                expected = ["submitted", "already_submitted" if same_response else "conflict"]
                self.assertCountEqual([result["state"] for result in results], expected)
                winner = next(index for index, result in enumerate(results)
                              if result["state"] == "submitted")
                stored = json.loads((self.root / "responses" / f"{request_id}.json").read_text(encoding="utf-8"))
                self.assertEqual(stored, {"version": 1, "request_id": request_id,
                                          "translations": replies[winner]})
                self.assertEqual(list((self.root / "responses").glob("*.tmp")), [])


class AgentJobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source with spaces.pdf"
        with pymupdf.open() as document:
            page = document.new_page()
            page.insert_text((50, 50), "A formula: E = mc2")
            document.save(self.source)
        self.engine = self.root / "fake-agent-engine.py"
        self.engine.write_text("#!" + sys.executable + "\n" + '''
import json, pathlib, shutil, sys, time
request = json.load(sys.stdin)
assert request['service'] == 'agent'
folder = pathlib.Path(request['output_directory'])
folder.mkdir()
exchange = pathlib.Path(request['fields']['--agent-exchange-directory'])
(exchange / 'requests').mkdir(parents=True, exist_ok=True)
request_id = 'a' * 32
pending = {
    'version': 1, 'request_id': request_id,
    'source_language': request['lang_in'], 'target_language': request['lang_out'],
    'instructions': 'Translate prose and preserve formula placeholders exactly.',
    'context': 'Mechanics paper, page 1.',
    'items': [
        {'id': '1', 'source': 'The mass matrix is {v1}.', 'kind': 'paragraph', 'is_short': False},
        {'id': '2', 'source': 'Preserve the original formula.', 'kind': 'paragraph', 'is_short': False}
    ]
}
temporary = exchange / 'requests' / (request_id + '.tmp')
temporary.write_text(json.dumps(pending), encoding='utf-8')
temporary.replace(temporary.with_suffix('.json'))
print(json.dumps({'type': 'progress', 'value': 0.2}), flush=True)
response = exchange / 'responses' / (request_id + '.json')
deadline = time.monotonic() + 10
while not response.is_file():
    if time.monotonic() > deadline: raise TimeoutError('Agent did not submit translations')
    time.sleep(0.02)
reply = json.loads(response.read_text(encoding='utf-8'))
assert reply['request_id'] == request_id
assert set(reply['translations']) == {'1', '2'}
assert reply['translations']['1'].count('{v1}') == 1
mono = folder / 'translated.pdf'
dual = folder / 'bilingual.pdf'
shutil.copyfile(request['input'], mono)
shutil.copyfile(request['input'], dual)
print(json.dumps({'type': 'finished', 'mono_pdf': str(mono), 'dual_pdf': str(dual)}), flush=True)
''', encoding="utf-8")
        self.engine.chmod(0o755)
        self.manager = JobManager(self.root / "state", self.engine)
        self.manager.start = partial(self.manager.start, hover_highlight=False)

    def tearDown(self):
        self.manager.shutdown()
        self.temp.cleanup()

    def wait_for(self, callback, predicate, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = callback()
            if predicate(result):
                return result
            time.sleep(0.02)
        self.fail("Agent job did not reach the expected state")

    def test_agent_job_gets_requests_submits_and_finishes(self):
        original = self.source.read_bytes()
        job = self.manager.start(str(self.source), str(self.root / "output"))
        self.assertEqual(job["service"], "agent", "Agent translation is the default")
        pending = self.wait_for(lambda: self.manager.pending(job["job_id"]),
                                lambda value: bool(value["requests"]))
        self.assertEqual(pending["state"], "waiting_for_translation")
        self.assertEqual(pending["requests"][0]["items"], envelope()["items"])
        result = self.manager.submit(job["job_id"], REQUEST_ID, TRANSLATIONS)
        self.assertEqual(result["state"], "submitted")
        status = self.wait_for(lambda: self.manager.get(job["job_id"]),
                               lambda value: value["state"] in TERMINAL)
        self.assertEqual(status["state"], "completed", status)
        self.assertEqual(set(status["artifacts"]), {"mono_pdf", "dual_pdf"})
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(self.manager.pending(job["job_id"])["requests"], [])
        with self.assertRaises(ValueError):
            self.manager.submit(job["job_id"], REQUEST_ID, TRANSLATIONS)

    def test_cancelled_job_rejects_agent_submissions(self):
        job = self.manager.start(str(self.source), str(self.root / "output"))
        self.wait_for(lambda: self.manager.pending(job["job_id"]),
                      lambda value: bool(value["requests"]))
        self.manager.cancel(job["job_id"])
        status = self.wait_for(lambda: self.manager.get(job["job_id"]),
                               lambda value: value["state"] in TERMINAL)
        self.assertEqual(status["state"], "cancelled", status)
        self.assertEqual(self.manager.pending(job["job_id"])["requests"], [])
        with self.assertRaises(ValueError):
            self.manager.submit(job["job_id"], REQUEST_ID, TRANSLATIONS)

    def test_agent_roundtrip_over_real_mcp_stdio(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        async def scenario():
            params = StdioServerParameters(
                command=sys.executable, args=["-m", "server", "serve"], cwd=str(ROOT),
                env=dict(os.environ, FOLIO_TRANSLATE_ENGINE=str(self.engine),
                         FOLIO_TRANSLATE_STATE_DIR=str(self.root / "mcp-state")))
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tool_list = await session.list_tools()
                    start = next(tool for tool in tool_list.tools if tool.name == "start_translation")
                    self.assertEqual(start.inputSchema["properties"]["service"]["default"], "agent")
                    result = await session.call_tool("start_translation", {
                        "input_path": str(self.source), "output_directory": str(self.root / "mcp-output"), "hover_highlight": False})
                    self.assertFalse(result.isError, result)
                    job_id = result.structuredContent["job_id"]
                    for _ in range(100):
                        pending = await session.call_tool("get_pending_translations", {"job_id": job_id})
                        self.assertFalse(pending.isError, pending)
                        if pending.structuredContent["requests"]:
                            break
                        await asyncio.sleep(0.03)
                    self.assertEqual(pending.structuredContent["requests"][0]["request_id"], REQUEST_ID)
                    invalid = await session.call_tool("submit_translations", {
                        "job_id": job_id, "request_id": REQUEST_ID,
                        "translations": {**TRANSLATIONS, "1": "缺少公式占位符。"}})
                    self.assertTrue(invalid.isError, invalid)
                    result = await session.call_tool("submit_translations", {
                        "job_id": job_id, "request_id": REQUEST_ID, "translations": TRANSLATIONS})
                    self.assertFalse(result.isError, result)
                    self.assertEqual(result.structuredContent["state"], "submitted")
                    for _ in range(100):
                        result = await session.call_tool("get_translation_status", {"job_id": job_id})
                        self.assertFalse(result.isError, result)
                        status = result.structuredContent
                        if status["state"] in TERMINAL:
                            break
                        await asyncio.sleep(0.03)
                    self.assertEqual(status["state"], "completed", status)
                    self.assertEqual(set(status["artifacts"]), {"mono_pdf", "dual_pdf"})
                    late = await session.call_tool("submit_translations", {
                        "job_id": job_id, "request_id": REQUEST_ID, "translations": TRANSLATIONS})
                    self.assertTrue(late.isError, late)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
