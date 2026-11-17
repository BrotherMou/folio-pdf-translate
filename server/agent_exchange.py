"""Local batches translated by the calling Agent, with no model/API invocation."""
from collections import Counter
import json
import os
from pathlib import Path
import re
import tempfile
from .sentences import expand


def read_request(exchange_directory: Path, request_id: str) -> dict:
    if not re.fullmatch(r"[a-f0-9]{32}", request_id):
        raise ValueError("Invalid request_id")
    path = Path(exchange_directory) / "requests" / f"{request_id}.json"
    request = json.loads(path.read_text(encoding="utf-8"))
    if request.get("version") != 1 or request.get("request_id") != request_id:
        raise ValueError("Invalid translation request envelope")
    items = request.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("Translation request has no items")
    ids = [item.get("id") for item in items]
    if any(not isinstance(key, str) for key in ids) or len(set(ids)) != len(ids):
        raise ValueError("Translation request has invalid item IDs")
    if any(not isinstance(item.get("source"), str) for item in items):
        raise ValueError("Translation request has invalid source text")
    return expand(request) if (Path(exchange_directory) / "sentence-mode").is_file() else request


def pending_requests(exchange_directory: Path, limit: int = 1) -> list[dict]:
    if not 1 <= limit <= 8:
        raise ValueError("limit must be within 1..8")
    root = Path(exchange_directory)
    result = []
    for path in sorted((root / "requests").glob("*.json")):
        if not (root / "responses" / path.name).exists():
            result.append(read_request(root, path.stem))
            if len(result) >= limit:
                break
    return result


def submit_response(exchange_directory: Path, request_id: str, translations: dict[str, str]) -> dict:
    root = Path(exchange_directory)
    request = read_request(root, request_id)
    expected = {item["id"]: item["source"] for item in request["items"]}
    if not isinstance(translations, dict) or set(translations) != set(expected):
        raise ValueError("translations must contain exactly the request's item IDs")
    for key, source in expected.items():
        value = translations[key]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Translation {key} must be a non-empty string")
        if Counter(re.findall(r"\{v[0-9]+\}", source)) != Counter(re.findall(r"\{v[0-9]+\}", value)):
            raise ValueError(f"Translation {key} changed, omitted, or duplicated formula/page placeholders")
    if request.get("sentence_alignment"):
        parents = {}
        for item in request["items"]:
            parent = parents.setdefault(item["paragraph_id"], {"source": item["paragraph_source"], "sentences": []})
            parent["sentences"].append({"source": item["source"], "translation": translations[item["id"]]})
        # Commit the exact sentence pairs before unblocking the native renderer. No extra fields in its envelope.
        publish(root / "alignments", request_id, {"version": 1, "request_id": request_id, "items": list(parents.values())})
        translations = {key: " ".join(s["translation"] for s in parent["sentences"]) for key, parent in parents.items()}
    response = {"version": 1, "request_id": request_id, "translations": translations}
    return publish(root / "responses", request_id, response)


def publish(folder: Path, request_id: str, response: dict) -> dict:
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = folder / f"{request_id}.json"
    if destination.exists():
        if json.loads(destination.read_text(encoding="utf-8")) == response:
            return {"request_id": request_id, "state": "already_submitted"}
        raise ValueError("A different response has already been submitted; start a new job to revise it")
    # Publish a complete file without overwriting another process's submission.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=folder,
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(response, stream, ensure_ascii=False)
        try:
            os.link(temporary, destination)
        except FileExistsError:
            if json.loads(destination.read_text(encoding="utf-8")) != response:
                raise ValueError("A different response has already been submitted; start a new job to revise it")
            return {"request_id": request_id, "state": "already_submitted"}
        except OSError as error:
            raise RuntimeError("Cannot atomically publish the Agent response on this filesystem. "
                               "Use a writable local directory with hard-link support (APFS or NTFS) for a new job.") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"request_id": request_id, "state": "submitted"}
