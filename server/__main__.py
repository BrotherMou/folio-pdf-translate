"""CLI: python -m server translate input.pdf --output-dir output; python -m server serve."""
import argparse
import json
import sys
import time

from .jobs import JobManager, TERMINAL
from .agent_exchange import pending_requests, submit_response
from pathlib import Path


def pairs(values):
    result = {}
    for value in values:
        key, sep, item = value.partition("=")
        if not sep or not key:
            raise ValueError("Options must use KEY=VALUE")
        result[key] = item
    return result


def main():
    parser = argparse.ArgumentParser(description="Standalone bilingual PDF translation")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="Run MCP over stdio")
    pending = commands.add_parser("agent-pending", help="Read batches from a running Agent translation")
    pending.add_argument("--exchange-directory", required=True)
    submit = commands.add_parser("agent-submit", help="Submit an Agent's translations to a running job")
    submit.add_argument("--exchange-directory", required=True)
    submit.add_argument("--request-id", required=True)
    submit.add_argument("--translations-file", required=True, help="JSON object mapping item IDs to translated text")
    translate = commands.add_parser("translate", help="Translate and wait for outputs")
    translate.add_argument("input")
    translate.add_argument("--output-dir", required=True)
    translate.add_argument("--service", default="agent")
    translate.add_argument("--from", dest="source_language", default="en")
    translate.add_argument("--to", dest="target_language", default="zh")
    translate.add_argument("--pages")
    translate.add_argument("--field", action="append", default=[], help="Use --field=OPTION=VALUE")
    translate.add_argument("--secret-env", action="append", default=[], help="Use --secret-env=OPTION=ENV_NAME")
    translate.add_argument("--glossary-file")
    translate.add_argument("--translate-images", action="store_true")
    translate.add_argument("--no-hover-highlight", action="store_true", help="Generate a plain bilingual PDF; required for external translation services")
    args = parser.parse_args()
    if args.command == "serve":
        from .mcp_server import run
        run()
        return
    manager = JobManager()
    job_id = None
    try:
        if args.command == "agent-pending":
            print(json.dumps({"requests": pending_requests(Path(args.exchange_directory))}, ensure_ascii=False, indent=2))
            return
        if args.command == "agent-submit":
            translations = json.loads(Path(args.translations_file).read_text(encoding="utf-8"))
            print(json.dumps(submit_response(Path(args.exchange_directory), args.request_id, translations), ensure_ascii=False))
            return
        status = manager.start(args.input, args.output_dir, args.service, args.target_language,
                               args.source_language, args.pages, pairs(args.field),
                               pairs(args.secret_env), args.glossary_file, args.translate_images, not args.no_hover_highlight)
        job_id = status["job_id"]
        if args.service == "agent":
            print(json.dumps({"type": "translation_started", **status}, ensure_ascii=False), flush=True)
        previous = None
        while status["state"] not in TERMINAL:
            event = status.get("last_event")
            if event != previous:
                print(json.dumps(event, ensure_ascii=False), file=sys.stderr, flush=True)
                previous = event
            time.sleep(0.2)
            status = manager.get(job_id)
        print(json.dumps(status, ensure_ascii=False, indent=2))
        if status["state"] != "completed":
            raise SystemExit(1)
    except KeyboardInterrupt:
        if job_id:
            manager.cancel(job_id)
        raise SystemExit(130)
    except (ValueError, FileNotFoundError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
    finally:
        manager.shutdown()


if __name__ == "__main__":
    main()
