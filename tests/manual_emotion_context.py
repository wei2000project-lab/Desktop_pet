"""Opt-in live acceptance; sends only synthetic cases, never saves chat history.

Run from the repository root with --run-live --output <new-report.json>.
This is deliberately outside unittest discovery and stops on the first API error.
"""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai.emotion_response import EmotionResponseParser
from app.ai.errors import AIRequestError
from app.ai.prompt_builder import build_system_prompt
from app.ai.request_executor import AIRequestExecutor, RequestExecutionLimits
from app.settings.api_group_service import APIGroupService


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--run-live", action="store_true", help="Allow paid API requests")
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    if not args.run_live:
        cli.error("--run-live is required to send API requests")
    if args.output.exists():
        cli.error("Use a new report path to preserve earlier results")

    cases = json.loads((ROOT / "tests/fixtures/emotion_context_cases.json").read_text(encoding="utf-8"))
    snapshot = APIGroupService().resolve_request()
    prompt = build_system_prompt({
        "system_prompt": "你是 Nova 桌面助手。用繁體中文簡短回覆一至兩句。",
        "selected_personality": "catgirl_companion",
    }, emotion_enabled=True)
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "total": len(cases), "completed": 0, "semantic_matches": 0,
        "passed": 0, "results": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    save()
    for case in cases:
        parser = EmotionResponseParser()
        chunks = []
        try:
            raw = AIRequestExecutor(limits=RequestExecutionLimits(
                max_candidates=1, max_http_attempts=1, operation_timeout=25,
            )).execute(snapshot, [
                {"role": "system", "content": prompt},
                {"role": "user", "content": case["user"]},
            ], max_chars=0, on_chunk_cb=lambda chunk: chunks.append(parser.feed(chunk)))
            chunks.append(parser.finish())
            body = "".join(chunks)
            selected = parser.emotion.value if parser.emotion else None
            # Strict prompt format, including the immediate newline. The production
            # parser also accepts body whitespace after a correctly closed marker.
            valid_prefix = bool(re.match(r"\A\[\[emotion:(happy|surprised|squint|none)\]\]\r?\n", raw))
            hidden = "[[emotion:" not in body
            semantic_match = selected == case["expected"]
            passed = semantic_match and valid_prefix and hidden and bool(body.strip())
            report["results"].append(dict(
                case, emotion=selected, text=body, valid_prefix=valid_prefix,
                marker_hidden=hidden, semantic_match=semantic_match, passed=passed,
            ))
            report["completed"] += 1
            report["semantic_matches"] += int(semantic_match)
            report["passed"] += int(passed)
            print(f"{case['id']}: {selected}; passed={passed}", flush=True)
        except AIRequestError as error:
            report["results"].append(dict(
                case, error_category=error.category.value, http_status=error.http_status,
            ))
            print(f"{case['id']}: stopped ({error.category.value}, HTTP {error.http_status})", flush=True)
            save()
            return 2
        save()
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
