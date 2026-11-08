"""CLI for the control hour and for CI:

  python -m cqa fetch DEV                       # pull the dataset from the organisers' API (CQA_ORG_API_URL)
  python -m cqa fetch DEV --file data/dev_snapshot.json
  python -m cqa evaluate DEV [--ids p1-ru-001,…] [--only-unevaluated] [--second-opinion]
  python -m cqa export DEV dev                  # → results/dev/results.json (+ validation)
  python -m cqa prod PROD-XXXX                  # fetch → evaluate → export results/prod (expects 10) in one go
  python -m cqa validate results/prod/results.json --expect 10
  python -m cqa serve                           # API + static UI on :8000
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time

from .config import settings


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(prog="cqa")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch"); f.add_argument("group_id"); f.add_argument("--file"); f.add_argument("--url")
    e = sub.add_parser("evaluate"); e.add_argument("group_id"); e.add_argument("--ids"); e.add_argument("--only-unevaluated", action="store_true"); e.add_argument("--second-opinion", action="store_true"); e.add_argument("--parallel", type=int, default=2); e.add_argument("--checklist", type=int)
    x = sub.add_parser("export"); x.add_argument("group_id"); x.add_argument("target", choices=["dev", "prod"]); x.add_argument("--expect", type=int); x.add_argument("--checklist", type=int)
    p = sub.add_parser("prod"); p.add_argument("group_id"); p.add_argument("--expect", type=int, default=10); p.add_argument("--file"); p.add_argument("--parallel", type=int, default=3)
    v = sub.add_parser("validate"); v.add_argument("path"); v.add_argument("--expect", type=int)
    s = sub.add_parser("serve"); s.add_argument("--port", type=int, default=8000); s.add_argument("--host", default="127.0.0.1")
    sub.add_parser("providers")
    a = ap.parse_args(argv)

    from . import pipeline
    if a.cmd == "fetch":
        r = pipeline.ingest(a.group_id, url=a.url, file=a.file)
        print(json.dumps({k: v for k, v in r.items() if k != "ids"}, ensure_ascii=False)); print("ids:", ", ".join(r["ids"]))
    elif a.cmd == "evaluate":
        t0 = time.time()
        r = pipeline.evaluate_group(a.group_id, conversation_ids=a.ids.split(",") if a.ids else None, only_unevaluated=a.only_unevaluated, second_opinion=a.second_opinion,
                                    parallel_dialogs=a.parallel, checklist_version_id=a.checklist, progress=lambda p: print(f"  {p['done']}/{p['total']}  {p['last']}  ${p['cost_usd']:.3f}", flush=True))
        for ev in sorted(r["evaluations"], key=lambda e: e["conversation_id"]):
            sc = ev.get("score") or {}
            print(f"{ev['conversation_id']:<12} {ev['status']:<6} {'' if sc.get('final_score') is None else f'{sc['final_score']:>6.2f}'} {'CRIT' if sc.get('critical_flag') else ''} {ev.get('error') or ''}")
        print(f"ok={r['ok']} error={r['error']} cost=${r['cost_usd']:.3f} time={time.time() - t0:.0f}s")
    elif a.cmd == "export":
        r = pipeline.export_group(a.group_id, a.target, expected_count=a.expect, checklist_version_id=a.checklist)
        print(json.dumps(r, ensure_ascii=False, indent=2)); return 0 if r["valid"] else 2
    elif a.cmd == "prod":
        t0 = time.time()
        r = pipeline.ingest(a.group_id, file=a.file); print(f"[{time.time() - t0:5.0f}s] fetched {r['records']} dialogs:", ", ".join(r["ids"]))
        r2 = pipeline.evaluate_group(a.group_id, parallel_dialogs=a.parallel, progress=lambda p: print(f"[{time.time() - t0:5.0f}s] {p['done']}/{p['total']} {p['last']} ${p['cost_usd']:.3f}", flush=True))
        print(f"[{time.time() - t0:5.0f}s] evaluated ok={r2['ok']} error={r2['error']} cost=${r2['cost_usd']:.3f}")
        r3 = pipeline.export_group(a.group_id, "prod", expected_count=a.expect)
        print(f"[{time.time() - t0:5.0f}s] export {r3['path']} valid={r3['valid']}")
        for pr in r3["problems"]:
            print("  PROBLEM:", pr)
        return 0 if r3["valid"] else 2
    elif a.cmd == "validate":
        from .export import validate_results
        doc = json.load(open(a.path, encoding="utf-8"))
        problems = validate_results(doc, expected_count=a.expect)
        print("VALID" if not problems else "INVALID"); [print(" -", p) for p in problems]; return 0 if not problems else 2
    elif a.cmd == "providers":
        from .llm.router import build_router
        r = build_router()
        for p in r.providers:
            print(f"{p.id:<10} {p.model:<28} {p.mode:<13} health={'ok' if p.health() else 'FAIL'}")
        if r.second_opinion:
            print(f"second opinion: {r.second_opinion.id} {r.second_opinion.model} health={'ok' if r.second_opinion.health() else 'FAIL'}")
    elif a.cmd == "serve":
        import uvicorn
        uvicorn.run("cqa.api.app:app", host=a.host, port=a.port, reload=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
