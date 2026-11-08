"""High-level operations shared by the CLI, the API and the worker:
fetch a dataset, evaluate dialogs, export results. Pure functions over the DB session."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from sqlalchemy import select

from . import db
from .config import settings
from .datasource import fetch_dataset, load_file, records_of
from .evaluator import checklist_defs, evaluate_dialog
from .export import build_results, validate_results, write_results
from .llm.router import LLMRouter, build_router

log = logging.getLogger("cqa.pipeline")


def ingest(group_id: str, *, url: str | None = None, file: str | None = None) -> dict:
    if file:
        data, snap = load_file(file), None
    else:
        data, snap_path = fetch_dataset(group_id, url)
        snap = str(snap_path)
    records = records_of(data)
    with db.session() as s:
        new = db.upsert_dialogs(s, group_id, records, source="file" if file else "api", snapshot_path=snap)
    return {"group_id": group_id, "records": len(records), "new": new, "snapshot": snap, "ids": [r["conversation_id"] for r in records]}


def evaluate_group(group_id: str, *, conversation_ids: list[str] | None = None, checklist_version_id: int | None = None, router: LLMRouter | None = None,
                   only_unevaluated: bool = False, second_opinion: bool = False, parallel_dialogs: int = 2, job_id: int | None = None,
                   progress: Callable[[dict], None] | None = None) -> dict:
    router = router or build_router()
    with db.session() as s:
        cl = s.get(db.ChecklistVersion, checklist_version_id) if checklist_version_id else db.active_checklist(s)
        checklist = {"key": cl.key, "version": cl.version, **cl.definition}
        dialogs = list(s.scalars(select(db.Dialog).where(db.Dialog.group_id == group_id).order_by(db.Dialog.api_order)))
        if conversation_ids:
            want = set(conversation_ids); dialogs = [d for d in dialogs if d.conversation_id in want]
        if only_unevaluated:
            done = {e.conversation_id for e in db.latest_evaluations(s, group_id, cl.id) if e.status == "ok"}
            dialogs = [d for d in dialogs if d.conversation_id not in done]
        items = [(d.id, db.dialog_record(d)) for d in dialogs]
        cl_id = cl.id
    results = {"group_id": group_id, "checklist_version_id": cl_id, "total": len(items), "ok": 0, "error": 0, "cost_usd": 0.0, "fallback_calls": 0, "evaluations": []}

    def work(item):
        dialog_id, rec = item
        res = evaluate_dialog(rec, checklist, router, second_opinion=second_opinion)
        with db.session() as s:
            d = s.get(db.Dialog, dialog_id); cl2 = s.get(db.ChecklistVersion, cl_id)
            ev = db.save_evaluation(s, d, cl2, res, job_id=job_id)
            res["evaluation_id"] = ev.id
        return res

    with ThreadPoolExecutor(max_workers=max(1, parallel_dialogs)) as ex:
        futures = [ex.submit(work, it) for it in items]
        for f in as_completed(futures):
            try:
                res = f.result()
            except Exception as e:  # noqa: BLE001
                log.exception("dialog evaluation crashed")
                res = {"conversation_id": "?", "status": "error", "error": str(e), "cost_usd": 0.0}
            results["evaluations"].append(res)
            results["ok" if res["status"] == "ok" else "error"] += 1
            results["cost_usd"] += res.get("cost_usd", 0.0)
            results["fallback_calls"] += (res.get("model") or {}).get("fallback_calls", 0)
            if progress:
                progress({"done": results["ok"] + results["error"], "total": results["total"], "failed": results["error"], "cost_usd": results["cost_usd"], "last": res["conversation_id"]})
    if results["fallback_calls"]:
        log.warning("%d criterion verdicts came from a FALLBACK provider (primary failed: credits, rate limit or network); "
                    "results.json shows mode/name accordingly. Re-run those dialogs when the primary is back.", results["fallback_calls"])
    return results


def export_group(group_id: str, target: str, *, checklist_version_id: int | None = None, expected_count: int | None = None) -> dict:
    with db.session() as s:
        cl = s.get(db.ChecklistVersion, checklist_version_id) if checklist_version_id else db.active_checklist(s)
        defs = checklist_defs({"criteria": cl.definition["criteria"]})
        evs = db.latest_evaluations(s, group_id, cl.id)
        dialogs = {d.conversation_id: d for d in s.scalars(select(db.Dialog).where(db.Dialog.group_id == group_id).order_by(db.Dialog.api_order))}
        order = list(dialogs.keys())
        by_id = {e.conversation_id: e for e in evs}
        evaluations = []
        modes: set[str] = set(); names: set[str] = set()
        for cid in order:
            e = by_id.get(cid)
            if e is None:
                evaluations.append({"conversation_id": cid, "status": "error", "error": "not evaluated"}); continue
            evaluations.append({"conversation_id": cid, "status": e.status, "error": e.error, "criteria": e.criteria, "score": e.score})
            if e.model:
                for u in (e.model.get("used") or [{"provider": e.model.get("provider"), "model": e.model.get("name"), "mode": e.model.get("mode", "external_api")}]):
                    modes.add(u["mode"]); names.add(f"{u['provider']}/{u['model']}")
            if e.second_opinion:
                modes.add("local"); names.update(v.get("model", "") for v in e.second_opinion.values() if isinstance(v, dict) and v.get("model"))
        if len(modes) > 1:
            modes = {"hybrid"}
        doc = build_results(evaluations, defs, modes=modes or {"external_api"}, model_name=" + ".join(sorted(n for n in names if n)) or "unknown")
        problems = validate_results(doc, expected_ids=order, expected_count=expected_count, transcripts={cid: len(d.transcript) for cid, d in dialogs.items()})
        path = write_results(doc, target)
        s.add(db.ExportRun(target=target, group_id=group_id, path=str(path), records=len(doc["results"]), valid=not problems, problems=problems))
    return {"path": str(path), "records": len(doc["results"]), "valid": not problems, "problems": problems, "model": doc["model"]}
