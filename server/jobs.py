"""A small local job runner shared by the CLI and MCP server.

Status files survive restarts. Processes do not: orderly server shutdown cancels
active jobs, and an unfinished status loaded after restart is marked interrupted.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
import uuid

from .agent_exchange import pending_requests, submit_response

ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {"completed", "failed", "cancelled", "interrupted"}
WINDOWS = sys.platform == "win32"
DEFAULT_STATE = ((Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "FolioPDFTranslate/jobs")
                 if WINDOWS else Path.home() / "Library/Application Support/FolioPDFTranslate/jobs")


def primary_artifact(status: dict) -> dict | None:
    """One deliverable after completion; the artifact index remains internal."""
    path = status.get("artifacts", {}).get("dual_pdf")
    if status["state"] != "completed" or not path:
        return None
    return {"path": path,
            "kind": "bilingual_hover_pdf" if status.get("hover_highlight") else "bilingual_pdf",
            "pages": status.get("pages")}


class JobManager:
    def __init__(self, state_dir: Path | None = None, engine: Path | None = None):
        self.state_dir = Path(state_dir or os.environ.get(
            "FOLIO_TRANSLATE_STATE_DIR", DEFAULT_STATE))
        self.engine = Path(engine or os.environ.get("FOLIO_TRANSLATE_ENGINE",
                           ROOT / "bin" / ("windows/pdf-translate-engine.exe" if WINDOWS else "pdf-translate-engine")))
        self.lock = threading.RLock()
        self.jobs: dict[str, dict] = {}
        self.stopping = False

    def _save(self, job: dict, **changes) -> dict:
        with self.lock:
            job["status"].update(changes, updated_at=time.time())
            status = job["status"]
            status["primary_artifact"] = primary_artifact(status)
            self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            target = self.state_dir / (status["job_id"] + ".json")
            temporary = target.with_suffix(".tmp")
            temporary.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.chmod(0o600)
            temporary.replace(target)
            return dict(status)

    def start(self, input_path: str, output_directory: str, service: str = "agent",
              target_language: str = "zh", source_language: str = "en",
              pages: str | None = None,
              fields: dict[str, str] | None = None,
              secret_env: dict[str, str] | None = None,
              glossary_file: str | None = None, translate_images: bool = False,
              hover_highlight: bool = True) -> dict:
        import pymupdf

        source = Path(input_path).expanduser().resolve(strict=True)
        if not source.is_file() or source.suffix.lower() != ".pdf":
            raise ValueError("input_path must be an existing PDF file")
        with pymupdf.open(source) as document:
            if document.needs_pass:
                raise ValueError("Password-protected PDFs are not supported")
            if len(document) < 1:
                raise ValueError("PDF has no pages")
            count = len(document)
        selected_pages = set(range(1, count + 1))
        if pages:
            if not re.fullmatch(r"\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*", pages):
                raise ValueError("pages must use 1-based numbers, for example 1,3-5")
            selected_pages = set()
            for group in pages.split(","):
                values = [int(n) for n in group.split("-")]
                if min(values) < 1 or max(values) > count or values[0] > values[-1]:
                    raise ValueError(f"pages must be within 1..{count} with increasing ranges")
                selected_pages.update(range(values[0], values[-1] + 1))
        with pymupdf.open(source) as document:
            no_text = [number for number in sorted(selected_pages)
                       if not document[number - 1].get_text("text").strip()]
        if no_text:
            raise ValueError("No extractable text on selected PDF pages: " + ", ".join(map(str, no_text))
                             + ". Image-only/scanned pages need OCR before translation; blank pages may be excluded "
                             "with the pages option. This version does not run OCR.")
        if not self.engine.is_file() or not os.access(self.engine, os.X_OK):
            script = "scripts/setup.ps1" if WINDOWS else "scripts/build-engine.sh"
            raise ValueError(f"Translation engine is missing; run {script} first")
        if service not in {"agent", "google", "bing", "openai", "openaicompatible", "ollama", "deepseek"}:
            raise ValueError("Unsupported service; choose agent, google, bing, openai, openaicompatible, ollama, or deepseek")
        if service == "agent" and (fields or secret_env or translate_images):
            raise ValueError("Agent translation does not accept provider fields, credentials, or image OCR")
        if hover_highlight and service != "agent":
            raise ValueError("Sentence hover requires service=agent; set hover_highlight=false for external services")
        if not target_language or not source_language:
            raise ValueError("Language codes cannot be empty")
        fields = dict(fields or {})
        if any(re.search(r"(?:key|token|secret|password)", key, re.I) for key in fields):
            raise ValueError("Pass credentials through secret_env, not fields")
        secrets = {}
        for key, name in (secret_env or {}).items():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                raise ValueError("secret_env values must be environment variable names")
            if not os.environ.get(name):
                raise ValueError(f"Required credential environment variable is empty: {name}")
            secrets[key] = os.environ[name]
        glossary = None
        if glossary_file:
            glossary = Path(glossary_file).expanduser().resolve(strict=True)
            if not glossary.is_file():
                raise ValueError("glossary_file must be a file")
        output_root = Path(output_directory).expanduser().resolve()
        with self.lock:
            if self.stopping:
                raise RuntimeError("Server is stopping")
            job_id = uuid.uuid4().hex
            folder = output_root / f"{source.stem}-{job_id[:12]}"
            folder.mkdir(parents=True, exist_ok=False, mode=0o700)
            exchange = folder / "agent-exchange" if service == "agent" else None
            if exchange is not None:
                (exchange / "requests").mkdir(parents=True, mode=0o700)
                (exchange / "responses").mkdir(mode=0o700)
                if hover_highlight:
                    (exchange / "sentence-mode").touch()
                fields["--agent-exchange-directory"] = str(exchange)
            request = {"input": str(source), "output_directory": str(folder / "pdf"),
                       "service": service, "fields": fields, "secrets": secrets,
                       "pages": pages, "lang_in": source_language, "lang_out": target_language,
                       "outputs": "both", "translate_images": translate_images,
                       "cache_directory": str(folder / ".cache"),
                       "glossary_file": str(glossary) if glossary else None}
            job = {"status": {"job_id": job_id, "state": "queued", "progress": 0,
                              "input": str(source), "output_directory": str(folder),
                              "service": service, "source_language": source_language,
                              "target_language": target_language, "pages": pages,
                              "hover_highlight": hover_highlight,
                              "agent_exchange_directory": str(exchange) if exchange else None,
                              "artifacts": {}, "warnings": [], "created_at": time.time()},
                   "cancel": threading.Event(), "process": None}
            self.jobs[job_id] = job
            self._save(job)
            thread = threading.Thread(target=self._run, args=(job, request), daemon=True)
            job["thread"] = thread
            thread.start()
            return dict(job["status"])

    def get(self, job_id: str) -> dict:
        if not re.fullmatch(r"[a-f0-9]{32}", job_id):
            raise ValueError("Invalid job_id")
        with self.lock:
            if job_id in self.jobs:
                job = self.jobs[job_id]
                status = job["status"]
                if status["service"] == "agent" and status["state"] in {"running", "waiting_for_translation"}:
                    pending = pending_requests(Path(status["agent_exchange_directory"]))
                    state = "waiting_for_translation" if pending else "running"
                    if state != status["state"]:
                        self._save(job, state=state)
                return dict(status)
            path = self.state_dir / f"{job_id}.json"
            if not path.is_file():
                raise ValueError("Unknown job_id")
            status = json.loads(path.read_text(encoding="utf-8"))
            # Older saved jobs predate the delivery marker; expose the same contract.
            status["primary_artifact"] = primary_artifact(status)
            if status["state"] not in TERMINAL:
                job = {"status": status}
                return self._save(job, state="interrupted", error="Server stopped before the job finished")
            return status

    def pending(self, job_id: str, limit: int = 1) -> dict:
        with self.lock:
            status = self.get(job_id)
            if status["service"] != "agent":
                raise ValueError("This job uses a translation service, not the calling Agent")
            requests = [] if status["state"] in TERMINAL | {"cancelling"} else pending_requests(
                Path(status["agent_exchange_directory"]), limit)
            return {"job_id": job_id, "state": status["state"], "requests": requests}

    def submit(self, job_id: str, request_id: str, translations: dict[str, str]) -> dict:
        with self.lock:
            status = self.get(job_id)
            if status["service"] != "agent" or status["state"] in TERMINAL | {"cancelling"}:
                raise ValueError("Translations can only be submitted to an active Agent translation job")
            return {"job_id": job_id, **submit_response(Path(status["agent_exchange_directory"]),
                                                       request_id, translations)}

    def cancel(self, job_id: str) -> dict:
        with self.lock:
            status = self.get(job_id)
            if status["state"] in TERMINAL:
                return status
            job = self.jobs[job_id]
            job["cancel"].set()
            process = job["process"]
            self._save(job, state="cancelling")
            if process and process.poll() is None:
                self._terminate(process)
            return dict(job["status"])

    @staticmethod
    def _terminate(process: subprocess.Popen) -> None:
        if WINDOWS:
            # taskkill /T includes child provider processes; argv never passes through a shell.
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, check=False)
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        # The runner reaps the parent. Escalation is bounded and group-specific.
        def kill_later():
            time.sleep(1)
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        threading.Thread(target=kill_later, daemon=True).start()

    def shutdown(self) -> None:
        with self.lock:
            self.stopping = True
            ids = list(self.jobs)
        for job_id in ids:
            self.cancel(job_id)
        for job in list(self.jobs.values()):
            job["thread"].join(timeout=3)

    def _spawn(self, job: dict, command: list[str], *, stdin=False) -> subprocess.Popen:
        with self.lock:
            if job["cancel"].is_set():
                raise InterruptedError("Translation cancelled")
            platform_options = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS
                                else {"start_new_session": True})
            process = subprocess.Popen(command, stdin=subprocess.PIPE if stdin else subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, encoding="utf-8", errors="replace", **platform_options)
            job["process"] = process
            return process

    def _run(self, job: dict, request: dict) -> None:
        status = job["status"]
        folder = Path(status["output_directory"])
        secret_values = [value for value in request["secrets"].values() if value]
        def redact(text: str) -> str:
            for value in secret_values:
                text = text.replace(value, "[REDACTED]")
            return text
        try:
            self._save(job, state="running")
            command = ([sys.executable, str(self.engine)] if self.engine.suffix == ".py" else [str(self.engine)])
            process = self._spawn(job, command, stdin=True)
            assert process.stdin is not None and process.stdout is not None
            process.stdin.write(json.dumps(request, ensure_ascii=False))
            process.stdin.close()
            finished = None
            failed = None
            with (folder / "engine.log").open("w", encoding="utf-8") as log:
                for raw in process.stdout:
                    line = redact(raw.rstrip())
                    log.write(line + "\n")
                    log.flush()
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(event, dict):
                        continue
                    kind = event.get("type")
                    if kind == "finished":
                        finished = event
                    elif kind == "failed":
                        failed = event.get("message", "Translation engine failed")
                    elif kind == "cancelled":
                        job["cancel"].set()
                    elif kind in {"stage", "progress", "notice", "problem", "preview"}:
                        changes = {"last_event": event}
                        if kind in {"notice", "problem"}:
                            changes["warnings"] = status["warnings"] + [event]
                        if kind == "progress":
                            value = event.get("value", event.get("progress"))
                            if isinstance(value, (int, float)):
                                changes["progress"] = max(0, min(0.95, value * 0.95))
                        self._save(job, **changes)
            process.stdout.close()
            code = process.wait()
            if job["cancel"].is_set():
                raise InterruptedError("Translation cancelled")
            if code != 0 or failed or not finished:
                raise RuntimeError(failed or f"Engine exited with code {code} without valid completion")
            artifacts = {}
            for key in ("mono_pdf", "dual_pdf"):
                value = finished.get(key)
                if not value:
                    raise RuntimeError(f"Engine did not return {key}")
                artifact = Path(value).resolve(strict=True)
                if not artifact.is_relative_to(folder) or artifact.stat().st_size == 0:
                    raise RuntimeError("Engine returned an invalid output path")
                import pymupdf
                with pymupdf.open(artifact) as document:
                    if not len(document):
                        raise RuntimeError("Engine returned an empty PDF")
                artifacts[key] = str(artifact)
            coverage_path = Path(artifacts["mono_pdf"]).parent / "translation-coverage.json"
            if coverage_path.is_file():
                artifacts["coverage_report"] = str(coverage_path)
            hover = None
            if status.get("hover_highlight"):
                from .hover import build_hover
                self._save(job, state="building_hover", last_event={"type": "stage", "message": "Build bilingual sentence hover"})
                original_dual = artifacts["dual_pdf"]
                target, report_path, report = build_hover(status["input"], artifacts["mono_pdf"], original_dual,
                                                          status["agent_exchange_directory"], job["cancel"].is_set)
                artifacts.update(dual_pdf=target, plain_dual_pdf=original_dual, hover_report=report_path)
                hover = {"sentence_pairs": report["sentence_pairs"], "mapped_blocks": report["mapped_blocks"],
                         "total_blocks": report["total_blocks"], "skipped_count": len(report["skipped"]),
                         "acrobat_ui_verified": False}
                if report["skipped"]:
                    self._save(job, warnings=status["warnings"] + [{"type": "notice", "message":
                        f"Hover alignment has {len(report['skipped'])} exclusions; inspect hover_report. Unmatched text stays readable without hover."}])
            with self.lock:
                if job["cancel"].is_set():
                    raise InterruptedError("Translation cancelled")
                self._save(job, state="completed", progress=1, artifacts=artifacts,
                           hover=hover, review_required=True, review_note="Review formulas/layout and coverage_report exclusions against every source page, including headings, lists, algorithm prose and keywords. Hover coverage counts only translated blocks. Adobe hover and drag-copy require reader testing.")
        except InterruptedError:
            self._save(job, state="cancelled", error="Translation cancelled; partial files are not deliverables")
        except Exception as error:
            process = job.get("process")
            if process and process.poll() is None:
                self._terminate(process)
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
            self._save(job, state="cancelled" if job["cancel"].is_set() else "failed", error=redact(str(error)))
        finally:
            with self.lock:
                process = job["process"]
                if process:
                    if process.stdin:
                        process.stdin.close()
                    if process.stdout:
                        process.stdout.close()
                job["process"] = None
            request["secrets"].clear()
