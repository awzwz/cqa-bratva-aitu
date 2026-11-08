"""FastAPI application: REST API under /api, Prometheus metrics at /metrics and the static UI at /.
SERVICE=api serves requests and enqueues jobs; SERVICE=worker executes them; SERVICE=all does both."""
from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any

import httpx
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from sqlalchemy import func, select

from .. import db, pipeline
from ..checklist_default import DEFAULT_CHECKLIST
from ..config import ROOT, settings
from ..evaluator import checklist_defs
from ..llm.router import build_router
from ..preprocess import compute_facts, normalize
from ..scoring import compute_score, validate_answer

log = logging.getLogger("cqa.api")
app = FastAPI(title="CQA — Conversation Quality Analytics", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",")], allow_methods=["*"], allow_headers=["*"])

M_REQ = Counter("cqa_http_requests_total", "HTTP requests", ["path", "status"])
M_EVAL = Counter("cqa_evaluations_total", "Dialog evaluations", ["status"])
M_LAT = Histogram("cqa_evaluation_seconds", "Dialog evaluation latency", buckets=(2, 5, 10, 20, 40, 80, 160))
M_COST = Counter("cqa_llm_cost_usd_total", "LLM spend in USD")
M_QUEUE = Gauge("cqa_jobs_running", "Jobs currently running")

_router = None
_router_lock = threading.Lock()


def router():
    global _router
    with _router_lock:
        if _router is None:
            _router = build_router()
        return _router


@app.middleware("http")
async def metrics_mw(request, call_next):
    resp = await call_next(request)
    path = request.url.path if request.url.path.startswith("/api") else "/static"
    M_REQ.labels(re.sub(r"/\d+", "/{id}", path), resp.status_code).inc()
    return resp


def err(status: int, msg: str):
    raise HTTPException(status_code=status, detail=msg)


# ---------------------------------------------------------------- health, settings, metrics
@app.get("/api/health")
def health():
    db.engine()
    return {"ok": True, "service": settings.service, "version": app.version, "time": time.time()}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/settings")
def get_settings():
    chain = [p.strip() for p in settings.provider_chain.split(",") if p.strip()]
    return {
        "team_name": settings.team_name, "provider_chain": chain, "primary_model": settings.openai_model if chain and chain[0] == "openai" else chain[0] if chain else None,
        "second_opinion": settings.second_opinion_provider, "llm_parallel": settings.llm_parallel, "budget_usd": settings.llm_budget_usd, "mask_pii": settings.mask_pii,
        "org_api_configured": bool(settings.org_api_url), "database": settings.database_url.split("://")[0], "queue": "redis" if settings.redis_url else "in-process",
        "providers": [{"id": pid, "configured": bool(getattr(settings, f"{pid}_api_key", None)) or pid in ("ollama", "lmstudio", "rules")} for pid in ("openai", "anthropic", "gemini", "deepseek", "ollama", "lmstudio", "rules")],
    }


@app.post("/api/providers/check")
def providers_check():
    r = router()
    out = [{"id": p.id, "model": p.model, "mode": p.mode, "healthy": p.health(), "role": "primary" if i == 0 else f"fallback-{i}"} for i, p in enumerate(r.providers)]
    if r.second_opinion:
        out.append({"id": r.second_opinion.id, "model": r.second_opinion.model, "mode": r.second_opinion.mode, "healthy": r.second_opinion.health(), "role": "second-opinion"})
    return {"providers": out, "spent_usd": round(r.spent_usd, 4)}


# ---------------------------------------------------------------- datasets & conversations
@app.post("/api/datasets/fetch")
def datasets_fetch(body: dict = Body(...)):
    gid = (body.get("group_id") or "").strip()
    if not gid:
        err(400, "group_id required")
    try:
        r = pipeline.ingest(gid, url=body.get("url"), file=body.get("file"))
    except Exception as e:  # noqa: BLE001
        err(502, str(e))
    return r


@app.get("/api/datasets")
def datasets():
    with db.session() as s:
        rows = s.execute(select(db.Dialog.group_id, func.count(db.Dialog.id)).group_by(db.Dialog.group_id)).all()
        evs = dict(s.execute(select(db.Evaluation.group_id, func.count(db.Evaluation.id)).where(db.Evaluation.is_latest.is_(True), db.Evaluation.status == "ok", db.Evaluation.checklist_version_id == db.active_checklist(s).id).group_by(db.Evaluation.group_id)).all())
        last = {d.group_id: d.fetched_at.isoformat() for d in s.scalars(select(db.Dataset).order_by(db.Dataset.fetched_at))}
    return [{"group_id": g, "dialogs": n, "evaluated": evs.get(g, 0), "fetched_at": last.get(g)} for g, n in rows]


def _appeal_overrides(s, evaluation_id: int) -> dict[str, Any]:
    out = {}
    for a in s.scalars(select(db.Appeal).where(db.Appeal.evaluation_id == evaluation_id, db.Appeal.status == "decided", db.Appeal.decision == "change")):
        out[a.criterion_id] = a.new_value
    return out


def _final_score(cl_def: dict, ev: db.Evaluation, overrides: dict) -> dict | None:
    if ev.status != "ok":
        return None
    defs = checklist_defs({"criteria": cl_def["criteria"]})
    answers = {cid: r["value"] for cid, r in ev.criteria.items()}
    answers.update(overrides)
    sc = compute_score(defs, answers)
    return {"final_score": sc.total_float(), "critical_flag": sc.critical_flag}


@app.get("/api/conversations")
def conversations(group_id: str = Query("DEV"), language: str | None = None, channel: str | None = None, critical: bool | None = None, q: str | None = None):
    with db.session() as s:
        dialogs = list(s.scalars(select(db.Dialog).where(db.Dialog.group_id == group_id).order_by(db.Dialog.api_order)))
        evs = {e.conversation_id: e for e in db.latest_evaluations(s, group_id, db.active_checklist(s).id)}
        appeals = {}
        for a in s.scalars(select(db.Appeal).where(db.Appeal.conversation_id.in_([d.conversation_id for d in dialogs]))):
            appeals.setdefault(a.conversation_id, []).append({"id": a.id, "status": a.status, "criterion_id": a.criterion_id})
        cls = {c.id: c for c in s.scalars(select(db.ChecklistVersion))}
        out = []
        for d in dialogs:
            if language and d.language != language.upper():
                continue
            if channel and d.channel != channel:
                continue
            e = evs.get(d.conversation_id)
            ops = [t for t in d.transcript if t.get("speaker") == "operator"]
            op_name = None
            if ops:
                m = re.search(r"(?:меня зовут|я|мен|I'?m|my name is)\s+([A-ZА-ЯЁӘҒҚҢӨҰҮІ][\w-]+)", ops[0].get("text", ""), re.I)
                op_name = m.group(1).strip(".,!") if m else None
                if "[имя скрыто]" in ops[0].get("text", "").lower():
                    op_name = "[Имя скрыто]"
            item = {"conversation_id": d.conversation_id, "channel": d.channel, "language": d.language, "turns": len(d.transcript), "operator": op_name, "has_audio": bool(d.audio_url),
                    "evaluation": None, "appeals": appeals.get(d.conversation_id, [])}
            if e:
                ov = _appeal_overrides(s, e.id)
                fin = _final_score(cls[e.checklist_version_id].definition, e, ov) if ov else None
                item["evaluation"] = {"id": e.id, "status": e.status, "error": e.error, "final_score": (e.score or {}).get("final_score"), "critical_flag": (e.score or {}).get("critical_flag"),
                                      "final_after_appeals": fin, "model": e.model, "created_at": e.created_at.isoformat(), "checklist_version_id": e.checklist_version_id, "cost_usd": e.cost_usd}
                if critical is not None and bool(item["evaluation"]["critical_flag"]) != critical:
                    continue
            elif critical:
                continue
            if q and q.lower() not in d.conversation_id.lower() and not any(q.lower() in (t.get("text") or "").lower() for t in d.transcript):
                continue
            out.append(item)
    return out


@app.get("/api/conversations/{cid}")
def conversation(cid: str, group_id: str | None = None):
    with db.session() as s:
        q = select(db.Dialog).where(db.Dialog.conversation_id == cid)
        if group_id:
            q = q.where(db.Dialog.group_id == group_id)
        d = s.scalars(q.order_by(db.Dialog.id.desc())).first()
        if not d:
            err(404, "dialog not found")
        rec = db.dialog_record(d)
        turns = normalize(rec)
        active_id = db.active_checklist(s).id  # show the evaluation by the active checklist version first
        e = s.scalars(select(db.Evaluation).where(db.Evaluation.dialog_id == d.id, db.Evaluation.is_latest.is_(True))
                      .order_by((db.Evaluation.checklist_version_id == active_id).desc(), db.Evaluation.id.desc())).first()
        evaluation = None
        history = [{"id": x.id, "status": x.status, "final_score": (x.score or {}).get("final_score"), "checklist_version_id": x.checklist_version_id, "created_at": x.created_at.isoformat(), "is_latest": x.is_latest}
                   for x in s.scalars(select(db.Evaluation).where(db.Evaluation.dialog_id == d.id).order_by(db.Evaluation.id.desc()))]
        appeals = []
        if e:
            cl = s.get(db.ChecklistVersion, e.checklist_version_id)
            ov = _appeal_overrides(s, e.id)
            evaluation = {"id": e.id, "status": e.status, "error": e.error, "criteria": e.criteria, "score": e.score, "facts": e.facts, "model": e.model, "second_opinion": e.second_opinion,
                          "duration_ms": e.duration_ms, "cost_usd": e.cost_usd, "created_at": e.created_at.isoformat(), "checklist_version_id": e.checklist_version_id, "checklist_version": cl.version,
                          "overrides": ov, "final_after_appeals": _final_score(cl.definition, e, ov) if ov else None,
                          "calls": [{"criterion_id": c.criterion_id, "provider": c.provider, "model": c.model, "tokens_in": c.tokens_in, "tokens_out": c.tokens_out, "latency_ms": c.latency_ms, "cost_usd": c.cost_usd, "status": c.status}
                                    for c in s.scalars(select(db.LLMCallRow).where(db.LLMCallRow.evaluation_id == e.id))]}
            appeals = [appeal_dict(a) for a in s.scalars(select(db.Appeal).where(db.Appeal.evaluation_id == e.id).order_by(db.Appeal.id))]
        return {"dialog": {**rec, "group_id": d.group_id}, "turns": turns, "facts": compute_facts(rec, turns), "evaluation": evaluation, "history": history, "appeals": appeals}


# ---------------------------------------------------------------- checklists
def checklist_dict(c: db.ChecklistVersion) -> dict:
    return c.as_dict()


@app.get("/api/checklists")
def checklists():
    with db.session() as s:
        return [checklist_dict(c) for c in s.scalars(select(db.ChecklistVersion).order_by(db.ChecklistVersion.key, db.ChecklistVersion.version.desc()))]


@app.get("/api/checklists/default")
def checklist_default():
    return DEFAULT_CHECKLIST


@app.get("/api/checklists/{cl_id}")
def checklist(cl_id: int):
    with db.session() as s:
        c = s.get(db.ChecklistVersion, cl_id) or err(404, "checklist not found")
        return checklist_dict(c)


def validate_definition(d: dict) -> dict:
    crit = d.get("criteria")
    if not isinstance(crit, list) or not crit:
        err(400, "criteria must be a non-empty list")
    ids = set()
    for c in crit:
        for k in ("id", "title", "type"):
            if not c.get(k):
                err(400, f"criterion missing {k}")
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,40}", c["id"]):
            err(400, f"bad criterion id {c['id']!r} (a-z, 0-9, _)")
        if c["id"] in ids:
            err(400, f"duplicate criterion id {c['id']}")
        ids.add(c["id"])
        if c["type"] not in ("binary", "scale", "flag"):
            err(400, f"{c['id']}: type must be binary|scale|flag")
        c["weight"] = int(c.get("weight", 0) or 0)
        if c["type"] == "scale":
            steps = c.get("scale") or []
            if len(steps) < 2 or any(not isinstance(s, (list, tuple)) or len(s) != 2 for s in steps):
                err(400, f"{c['id']}: scale needs ≥2 [step, description] pairs")
            c["scale"] = sorted(([int(s[0]), str(s[1])] for s in steps), key=lambda x: -x[0])
        if c["type"] == "flag":
            c["weight"] = 0; c["allow_na"] = False
    if sum(c["weight"] for c in crit if c["type"] != "flag") <= 0:
        err(400, "sum of weights must be positive")
    d.setdefault("general_rules", DEFAULT_CHECKLIST["general_rules"])
    d.setdefault("sections", sorted({c.get("section", "") for c in crit}))
    return {k: d[k] for k in ("general_rules", "sections", "criteria")}


@app.post("/api/checklists")
def checklist_create(body: dict = Body(...)):
    """Create a new version: {base_id?, key?, name?, channel?, note?, created_by?, definition:{general_rules, sections, criteria}, activate?}"""
    definition = validate_definition(dict(body.get("definition") or {}))
    with db.session() as s:
        base = s.get(db.ChecklistVersion, body["base_id"]) if body.get("base_id") else None
        key = body.get("key") or (base.key if base else DEFAULT_CHECKLIST["key"])
        last = s.scalar(select(func.max(db.ChecklistVersion.version)).where(db.ChecklistVersion.key == key)) or 0
        row = db.ChecklistVersion(key=key, version=last + 1, name=body.get("name") or (base.name if base else DEFAULT_CHECKLIST["name"]), channel=body.get("channel") or (base.channel if base else "agent chat"),
                                  is_active=False, definition=definition, note=body.get("note"), created_by=body.get("created_by") or "ui")
        s.add(row); s.flush()
        if body.get("activate"):
            for other in s.scalars(select(db.ChecklistVersion).where(db.ChecklistVersion.key == key)):
                other.is_active = other.id == row.id
        s.commit()
        return checklist_dict(row)


@app.post("/api/checklists/{cl_id}/activate")
def checklist_activate(cl_id: int):
    with db.session() as s:
        row = s.get(db.ChecklistVersion, cl_id) or err(404, "not found")
        for other in s.scalars(select(db.ChecklistVersion).where(db.ChecklistVersion.key == row.key)):
            other.is_active = other.id == row.id
        s.commit()
        return checklist_dict(row)


@app.post("/api/checklists/{cl_id}/diff")
def checklist_diff(cl_id: int, body: dict = Body(...)):
    """Compare latest evaluations of a group under two checklist versions: {group_id, other_id}"""
    with db.session() as s:
        a = s.get(db.ChecklistVersion, cl_id) or err(404, "not found"); b = s.get(db.ChecklistVersion, int(body["other_id"])) or err(404, "other not found")
        ea = {e.conversation_id: e for e in db.latest_evaluations(s, body["group_id"], a.id)}
        eb = {e.conversation_id: e for e in db.latest_evaluations(s, body["group_id"], b.id)}
        rows = []
        for cid in sorted(set(ea) | set(eb)):
            x, y = ea.get(cid), eb.get(cid)
            sx = (x.score or {}).get("final_score") if x else None; sy = (y.score or {}).get("final_score") if y else None
            changed = [k for k in set((x.criteria if x else {}) | (y.criteria if y else {})) if (x.criteria.get(k, {}).get("value") if x else None) != (y.criteria.get(k, {}).get("value") if y else None)]
            rows.append({"conversation_id": cid, "score_a": sx, "score_b": sy, "delta": None if sx is None or sy is None else round(sy - sx, 2), "changed_criteria": sorted(changed)})
        return {"a": a.version, "b": b.version, "rows": rows}


# ---------------------------------------------------------------- jobs (evaluation)
JOBS_RUNNING: dict[int, dict] = {}


def run_job(job_id: int):
    M_QUEUE.inc()
    try:
        with db.session() as s:
            job = s.get(db.Job, job_id); job.status = "running"; job.started_at = db.now(); s.commit()
            gid, cl_id, ids, opts = job.group_id, job.checklist_version_id, list(job.conversation_ids or []), dict(job.options or {})

        def progress(p):
            with db.session() as s:
                j = s.get(db.Job, job_id); j.done = p["done"]; j.failed = p["failed"]; j.cost_usd = p["cost_usd"]; s.commit()
            JOBS_RUNNING[job_id] = p

        t0 = time.time()
        res = pipeline.evaluate_group(gid, conversation_ids=ids or None, checklist_version_id=cl_id, router=router(), only_unevaluated=opts.get("only_unevaluated", False),
                                      second_opinion=opts.get("second_opinion", False), parallel_dialogs=opts.get("parallel_dialogs", 2), job_id=job_id, progress=progress)
        for e in res["evaluations"]:
            M_EVAL.labels(e["status"]).inc()
        M_LAT.observe((time.time() - t0) / max(1, res["total"]))
        M_COST.inc(res["cost_usd"])
        with db.session() as s:
            job = s.get(db.Job, job_id); job.status = "done"; job.done = res["total"]; job.failed = res["error"]; job.cost_usd = res["cost_usd"]; job.finished_at = db.now(); s.commit()
    except Exception as e:  # noqa: BLE001
        log.exception("job %s failed", job_id)
        with db.session() as s:
            job = s.get(db.Job, job_id); job.status = "failed"; job.error = str(e); job.finished_at = db.now(); s.commit()
    finally:
        JOBS_RUNNING.pop(job_id, None)
        M_QUEUE.dec()


@app.post("/api/jobs", status_code=202)
def job_create(body: dict = Body(...)):
    gid = body.get("group_id") or "DEV"
    with db.session() as s:
        cl = s.get(db.ChecklistVersion, body["checklist_version_id"]) if body.get("checklist_version_id") else db.active_checklist(s)
        ids = body.get("conversation_ids") or []
        total = len(ids) if ids else s.scalar(select(func.count(db.Dialog.id)).where(db.Dialog.group_id == gid))
        job = db.Job(kind="evaluate", group_id=gid, checklist_version_id=cl.id, status="queued", total=total, conversation_ids=ids,
                     options={"only_unevaluated": bool(body.get("only_unevaluated")), "second_opinion": bool(body.get("second_opinion")), "parallel_dialogs": int(body.get("parallel_dialogs", 2))})
        s.add(job); s.commit(); jid = job.id
    if settings.service in ("all", "api") and not settings.redis_url:
        threading.Thread(target=run_job, args=(jid,), daemon=True).start()
    return job_dict_by_id(jid)


def job_dict(j: db.Job) -> dict:
    d = {"id": j.id, "kind": j.kind, "group_id": j.group_id, "checklist_version_id": j.checklist_version_id, "status": j.status, "total": j.total, "done": j.done, "failed": j.failed,
         "cost_usd": round(j.cost_usd, 4), "options": j.options, "error": j.error, "created_at": j.created_at.isoformat(), "started_at": j.started_at.isoformat() if j.started_at else None,
         "finished_at": j.finished_at.isoformat() if j.finished_at else None}
    if j.id in JOBS_RUNNING:
        d["last"] = JOBS_RUNNING[j.id].get("last")
    return d


def job_dict_by_id(jid: int) -> dict:
    with db.session() as s:
        return job_dict(s.get(db.Job, jid))


@app.get("/api/jobs")
def jobs(limit: int = 20):
    with db.session() as s:
        return [job_dict(j) for j in s.scalars(select(db.Job).order_by(db.Job.id.desc()).limit(limit))]


@app.get("/api/jobs/{jid}")
def job(jid: int):
    with db.session() as s:
        j = s.get(db.Job, jid) or err(404, "job not found")
        d = job_dict(j)
        d["evaluations"] = [{"conversation_id": e.conversation_id, "status": e.status, "final_score": (e.score or {}).get("final_score"), "critical_flag": (e.score or {}).get("critical_flag"), "cost_usd": e.cost_usd, "duration_ms": e.duration_ms}
                            for e in s.scalars(select(db.Evaluation).where(db.Evaluation.job_id == jid).order_by(db.Evaluation.id))]
        return d


@app.get("/api/llm-calls")
def llm_calls(conversation_id: str | None = None, job_id: int | None = None, limit: int = 200):
    with db.session() as s:
        q = select(db.LLMCallRow).order_by(db.LLMCallRow.id.desc()).limit(limit)
        if conversation_id:
            q = q.where(db.LLMCallRow.conversation_id == conversation_id)
        if job_id:
            ev_ids = [e.id for e in s.scalars(select(db.Evaluation).where(db.Evaluation.job_id == job_id))]
            q = q.where(db.LLMCallRow.evaluation_id.in_(ev_ids))
        return [{"id": c.id, "evaluation_id": c.evaluation_id, "conversation_id": c.conversation_id, "criterion_id": c.criterion_id, "provider": c.provider, "model": c.model, "prompt_sha256": c.prompt_sha256,
                 "tokens_in": c.tokens_in, "tokens_out": c.tokens_out, "latency_ms": c.latency_ms, "cost_usd": c.cost_usd, "status": c.status, "created_at": c.created_at.isoformat(), "response_text": c.response_text}
                for c in s.scalars(q)]


# ---------------------------------------------------------------- appeals
def appeal_dict(a: db.Appeal) -> dict:
    return {"id": a.id, "evaluation_id": a.evaluation_id, "conversation_id": a.conversation_id, "criterion_id": a.criterion_id, "proposed_value": a.proposed_value, "comment": a.comment,
            "submitted_by": a.submitted_by, "status": a.status, "decision": a.decision, "new_value": a.new_value, "reason": a.reason, "reviewer": a.reviewer, "score_before": a.score_before,
            "score_after": a.score_after, "created_at": a.created_at.isoformat(), "decided_at": a.decided_at.isoformat() if a.decided_at else None}


@app.get("/api/appeals")
def appeals(status: str | None = None, group_id: str | None = None):
    with db.session() as s:
        q = select(db.Appeal).order_by(db.Appeal.status.desc(), db.Appeal.id.desc())
        if status:
            q = q.where(db.Appeal.status == status)
        rows = list(s.scalars(q))
        if group_id:
            ev_ids = {e.id for e in s.scalars(select(db.Evaluation).where(db.Evaluation.group_id == group_id))}
            rows = [a for a in rows if a.evaluation_id in ev_ids]
        evs = {e.id: e for e in s.scalars(select(db.Evaluation).where(db.Evaluation.id.in_([a.evaluation_id for a in rows])))} if rows else {}
        out = []
        for a in rows:
            d = appeal_dict(a); e = evs.get(a.evaluation_id)
            d["ai_value"] = (e.criteria.get(a.criterion_id) or {}).get("value") if e else None
            d["ai_rationale"] = (e.criteria.get(a.criterion_id) or {}).get("rationale") if e else None
            out.append(d)
        return out


@app.post("/api/appeals", status_code=201)
def appeal_create(body: dict = Body(...)):
    with db.session() as s:
        e = s.get(db.Evaluation, int(body.get("evaluation_id", 0))) or err(404, "evaluation not found")
        cid = body.get("criterion_id") or err(400, "criterion_id required")
        if cid not in e.criteria:
            err(400, "criterion not in evaluation")
        if not (body.get("comment") or "").strip():
            err(400, "comment required")
        if s.scalar(select(func.count(db.Appeal.id)).where(db.Appeal.evaluation_id == e.id, db.Appeal.criterion_id == cid, db.Appeal.status == "open")):
            err(409, "an open appeal already exists for this criterion")
        cl = s.get(db.ChecklistVersion, e.checklist_version_id)
        c = next(x for x in checklist_defs({"criteria": cl.definition["criteria"]}) if x.id == cid)
        proposed = body.get("proposed_value", "__none__")
        if proposed != "__none__":
            try:
                proposed = validate_answer(c, proposed)
            except ValueError as ex:
                err(400, str(ex))
        else:
            proposed = None
        a = db.Appeal(evaluation_id=e.id, conversation_id=e.conversation_id, criterion_id=cid, proposed_value=proposed, comment=body["comment"].strip(), submitted_by=body.get("submitted_by") or "оператор",
                      score_before=(e.score or {}).get("final_score"))
        s.add(a); s.commit()
        return appeal_dict(a)


@app.post("/api/appeals/{aid}/decision")
def appeal_decide(aid: int, body: dict = Body(...)):
    """{decision: confirm|change, new_value?, reason, reviewer}"""
    with db.session() as s:
        a = s.get(db.Appeal, aid) or err(404, "appeal not found")
        if a.status != "open":
            err(409, "appeal already decided")
        decision = body.get("decision")
        if decision not in ("confirm", "change"):
            err(400, "decision must be confirm|change")
        if not (body.get("reason") or "").strip():
            err(400, "reason required")
        e = s.get(db.Evaluation, a.evaluation_id); cl = s.get(db.ChecklistVersion, e.checklist_version_id)
        defs = checklist_defs({"criteria": cl.definition["criteria"]}); c = next(x for x in defs if x.id == a.criterion_id)
        new_value = None
        if decision == "change":
            try:
                new_value = validate_answer(c, body.get("new_value"))
            except ValueError as ex:
                err(400, str(ex))
        a.status, a.decision, a.new_value, a.reason, a.reviewer, a.decided_at = "decided", decision, new_value, body["reason"].strip(), body.get("reviewer") or "проверяющий", db.now()
        s.flush()
        ov = _appeal_overrides(s, e.id)
        fin = _final_score(cl.definition, e, ov)
        a.score_after = fin["final_score"] if fin else None
        s.commit()
        d = appeal_dict(a); d["final_after_appeals"] = fin
        return d


# ---------------------------------------------------------------- export, stats, audio
@app.post("/api/export")
def export(body: dict = Body(...)):
    gid = body.get("group_id") or "DEV"; target = body.get("target") or ("prod" if gid != "DEV" else "dev")
    if target not in ("dev", "prod"):
        err(400, "target must be dev|prod")
    r = pipeline.export_group(gid, target, expected_count=body.get("expected_count"), checklist_version_id=body.get("checklist_version_id"))
    r["path"] = str(r["path"]).replace(str(ROOT) + "/", "")
    return r


@app.get("/api/export/runs")
def export_runs():
    with db.session() as s:
        return [{"id": r.id, "target": r.target, "group_id": r.group_id, "path": r.path.replace(str(ROOT) + "/", ""), "records": r.records, "valid": r.valid, "problems": r.problems, "created_at": r.created_at.isoformat()}
                for r in s.scalars(select(db.ExportRun).order_by(db.ExportRun.id.desc()).limit(20))]


@app.get("/api/export/preview")
def export_preview(group_id: str = "DEV"):
    from ..export import build_results, validate_results
    with db.session() as s:
        cl = db.active_checklist(s); defs = checklist_defs({"criteria": cl.definition["criteria"]})
        evs = db.latest_evaluations(s, group_id, cl.id)
        doc = build_results([{"conversation_id": e.conversation_id, "status": e.status, "error": e.error, "criteria": e.criteria, "score": e.score} for e in evs], defs, modes={e.model.get("mode", "external_api") for e in evs if e.model} or {"external_api"},
                            model_name=", ".join(sorted({f"{e.model.get('provider')}/{e.model.get('name')}" for e in evs if e.model})) or "unknown")
        return {"document": doc, "problems": validate_results(doc)}


@app.get("/api/stats")
def stats(group_id: str = "DEV"):
    with db.session() as s:
        evs = [e for e in db.latest_evaluations(s, group_id, db.active_checklist(s).id) if e.status == "ok" and e.score]
        dialogs = {d.conversation_id: d for d in s.scalars(select(db.Dialog).where(db.Dialog.group_id == group_id))}
        scores = [e.score["final_score"] for e in evs if e.score.get("final_score") is not None]
        cl = db.active_checklist(s); defs = checklist_defs({"criteria": cl.definition["criteria"]})
        pass_rate = []
        for c in defs:
            vals = [e.criteria.get(c.id, {}).get("value") for e in evs if c.id in e.criteria]
            applicable = [v for v in vals if v is not None]
            if c.type == "flag":
                pass_rate.append({"criterion_id": c.id, "code": c.code, "title": c.title, "flagged": sum(1 for v in applicable if v), "applicable": len(applicable)})
            else:
                top = c.top_step if c.type == "scale" else True
                pass_rate.append({"criterion_id": c.id, "code": c.code, "title": c.title, "pass": sum(1 for v in applicable if v == top), "applicable": len(applicable), "na": len(vals) - len(applicable)})
        by_lang: dict[str, list[float]] = {}
        for e in evs:
            d = dialogs.get(e.conversation_id)
            if d and e.score.get("final_score") is not None:
                by_lang.setdefault(d.language, []).append(e.score["final_score"])
        dist = {"0-40": 0, "40-60": 0, "60-80": 0, "80-90": 0, "90-100": 0}
        for sc in scores:
            dist["0-40" if sc < 40 else "40-60" if sc < 60 else "60-80" if sc < 80 else "80-90" if sc < 90 else "90-100"] += 1
        violations = []
        for e in evs:
            if e.score.get("critical_flag"):
                r = e.criteria.get("critical", {})
                violations.append({"conversation_id": e.conversation_id, "rationale": r.get("rationale"), "evidence_turns": r.get("evidence_turns"), "final_score": e.score.get("final_score"), "language": dialogs[e.conversation_id].language if e.conversation_id in dialogs else None})
        appeals = list(s.scalars(select(db.Appeal)))
        return {"group_id": group_id, "dialogs": len(dialogs), "evaluated": len(evs), "avg": round(sum(scores) / len(scores), 2) if scores else None, "median": sorted(scores)[len(scores) // 2] if scores else None,
                "critical": len(violations), "appeals_open": sum(1 for a in appeals if a.status == "open"), "appeals_decided": sum(1 for a in appeals if a.status == "decided"),
                "appeals_changed": sum(1 for a in appeals if a.decision == "change"), "pass_rate": pass_rate, "by_language": {k: {"n": len(v), "avg": round(sum(v) / len(v), 2)} for k, v in by_lang.items()},
                "distribution": dist, "violations": violations, "cost_usd": round(sum(e.cost_usd for e in evs), 4)}


@app.get("/api/audio/{cid}")
def audio(cid: str):
    """The organisers' audio_url is an HTML player page whose <source> carries a 60-minute SAS link.
    We fetch the page server-side and redirect the browser to the fresh mp3 URL."""
    with db.session() as s:
        d = s.scalars(select(db.Dialog).where(db.Dialog.conversation_id == cid).order_by(db.Dialog.id.desc())).first() or err(404, "dialog not found")
        if not d.audio_url:
            err(404, "no audio for this dialog")
        url = d.audio_url
    try:
        r = httpx.get(url, timeout=30, follow_redirects=True)
        m = re.search(r'<source[^>]+src="([^"]+)"', r.text)
        if m:
            return RedirectResponse(m.group(1).replace("&amp;", "&"), status_code=302)
        if r.headers.get("content-type", "").startswith("audio/"):
            return RedirectResponse(url, status_code=302)
    except Exception as e:  # noqa: BLE001
        err(502, f"audio fetch failed: {e}")
    err(502, "audio source not found in player page")


# ---------------------------------------------------------------- static UI (must be last)
FRONTEND = ROOT / "frontend"
if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="ui")
