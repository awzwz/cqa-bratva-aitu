"""Persistence: SQLAlchemy 2 models that run on SQLite (laptop) and PostgreSQL (compose/k8s).
JSON columns hold transcripts, checklist definitions and per-criterion results; every LLM call
is stored in llm_calls for the audit trail."""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .checklist_default import DEFAULT_CHECKLIST
from .config import settings


def now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(32))  # api | file
    snapshot_path: Mapped[str | None] = mapped_column(String(512))
    total_records: Mapped[int] = mapped_column(Integer, default=0)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Dialog(Base):
    __tablename__ = "dialogs"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(64), index=True)
    group_id: Mapped[str] = mapped_column(String(64), index=True)
    channel: Mapped[str] = mapped_column(String(32))
    language: Mapped[str] = mapped_column(String(8))
    audio_url: Mapped[str | None] = mapped_column(Text)
    transcript: Mapped[list] = mapped_column(JSON)
    api_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ChecklistVersion(Base):
    __tablename__ = "checklist_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200))
    channel: Mapped[str] = mapped_column(String(32), default="agent chat")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    definition: Mapped[dict] = mapped_column(JSON)
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    def as_dict(self) -> dict:
        d = dict(self.definition)
        d.update({"id": self.id, "key": self.key, "version": self.version, "name": self.name, "channel": self.channel, "is_active": self.is_active, "note": self.note, "created_at": self.created_at.isoformat()})
        return d


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))  # evaluate
    group_id: Mapped[str] = mapped_column(String(64))
    checklist_version_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued | running | done | failed | cancelled
    total: Mapped[int] = mapped_column(Integer, default=0)
    done: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    conversation_ids: Mapped[list] = mapped_column(JSON, default=list)
    options: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Evaluation(Base):
    __tablename__ = "evaluations"
    id: Mapped[int] = mapped_column(primary_key=True)
    dialog_id: Mapped[int] = mapped_column(ForeignKey("dialogs.id"), index=True)
    conversation_id: Mapped[str] = mapped_column(String(64), index=True)
    group_id: Mapped[str] = mapped_column(String(64), index=True)
    checklist_version_id: Mapped[int] = mapped_column(ForeignKey("checklist_versions.id"), index=True)
    job_id: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))  # ok | error
    error: Mapped[str | None] = mapped_column(Text)
    criteria: Mapped[dict] = mapped_column(JSON)  # {criterion_id: {value, rationale, evidence_turns, na_reason, expected_turn, confidence}}
    score: Mapped[dict | None] = mapped_column(JSON)  # {final_score, critical_flag, sections, rows}
    facts: Mapped[dict] = mapped_column(JSON, default=dict)
    second_opinion: Mapped[dict | None] = mapped_column(JSON)
    model: Mapped[dict] = mapped_column(JSON, default=dict)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    is_latest: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class LLMCallRow(Base):
    __tablename__ = "llm_calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int | None] = mapped_column(ForeignKey("evaluations.id"), index=True)
    conversation_id: Mapped[str] = mapped_column(String(64), index=True)
    criterion_id: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(120))
    prompt_sha256: Mapped[str] = mapped_column(String(64))
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16))
    response_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Appeal(Base):
    __tablename__ = "appeals"
    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id"), index=True)
    conversation_id: Mapped[str] = mapped_column(String(64), index=True)
    criterion_id: Mapped[str] = mapped_column(String(64))
    proposed_value: Mapped[Any | None] = mapped_column(JSON)
    comment: Mapped[str] = mapped_column(Text)
    submitted_by: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | decided
    decision: Mapped[str | None] = mapped_column(String(16))  # confirm | change
    new_value: Mapped[Any | None] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(Text)
    reviewer: Mapped[str | None] = mapped_column(String(120))
    score_before: Mapped[float | None] = mapped_column(Float)
    score_after: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExportRun(Base):
    __tablename__ = "export_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    target: Mapped[str] = mapped_column(String(16))  # dev | prod
    group_id: Mapped[str] = mapped_column(String(64))
    path: Mapped[str] = mapped_column(String(512))
    records: Mapped[int] = mapped_column(Integer)
    valid: Mapped[bool] = mapped_column(Boolean)
    problems: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


# ---------------------------------------------------------------- engine & helpers
_engine = None
_Session: sessionmaker | None = None


def engine():
    global _engine, _Session
    if _engine is None:
        url = settings.database_url
        kw = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {"pool_pre_ping": True, "pool_size": 5, "max_overflow": 10}
        _engine = create_engine(url, json_serializer=lambda o: json.dumps(o, ensure_ascii=False), **kw)
        Base.metadata.create_all(_engine)
        _Session = sessionmaker(_engine, expire_on_commit=False)
        with _Session() as s:
            ensure_default_checklist(s)
    return _engine


@contextmanager
def session():
    engine()
    assert _Session is not None
    with _Session() as s:
        yield s
        s.commit()


def ensure_default_checklist(s: Session) -> ChecklistVersion:
    row = s.scalar(select(ChecklistVersion).where(ChecklistVersion.key == DEFAULT_CHECKLIST["key"]).order_by(ChecklistVersion.version.desc()))
    if row:
        return row
    row = ChecklistVersion(key=DEFAULT_CHECKLIST["key"], version=1, name=DEFAULT_CHECKLIST["name"], channel=DEFAULT_CHECKLIST["channel"], is_active=True,
                           definition={k: v for k, v in DEFAULT_CHECKLIST.items() if k in ("general_rules", "sections", "criteria")}, note="Стартовая конфигурация из чек-листа заказчика", created_by="import")
    s.add(row); s.commit()
    return row


def active_checklist(s: Session, channel: str | None = None) -> ChecklistVersion:
    q = select(ChecklistVersion).where(ChecklistVersion.is_active.is_(True))
    rows = list(s.scalars(q))
    if channel:
        for r in rows:
            if r.channel == channel:
                return r
    return rows[0] if rows else ensure_default_checklist(s)


def upsert_dialogs(s: Session, group_id: str, records: list[dict], *, source: str, snapshot_path: str | None) -> int:
    s.add(Dataset(group_id=group_id, source=source, snapshot_path=snapshot_path, total_records=len(records)))
    existing = {d.conversation_id: d for d in s.scalars(select(Dialog).where(Dialog.group_id == group_id))}
    n = 0
    for i, r in enumerate(records):
        d = existing.get(r["conversation_id"])
        if d is None:
            d = Dialog(conversation_id=r["conversation_id"], group_id=group_id, channel=r["channel"], language=r["language"], audio_url=r.get("audio_url"), transcript=r["transcript"], api_order=i)
            s.add(d); n += 1
        else:
            d.channel, d.language, d.audio_url, d.transcript, d.api_order = r["channel"], r["language"], r.get("audio_url"), r["transcript"], i
    s.commit()
    return n


def dialog_record(d: Dialog) -> dict:
    return {"conversation_id": d.conversation_id, "channel": d.channel, "language": d.language, "transcript": d.transcript, "audio_url": d.audio_url}


def save_evaluation(s: Session, d: Dialog, cl: ChecklistVersion, result: dict, job_id: int | None = None) -> Evaluation:
    for old in s.scalars(select(Evaluation).where(Evaluation.dialog_id == d.id, Evaluation.checklist_version_id == cl.id, Evaluation.is_latest.is_(True))):
        old.is_latest = False
    ev = Evaluation(dialog_id=d.id, conversation_id=d.conversation_id, group_id=d.group_id, checklist_version_id=cl.id, job_id=job_id, status=result["status"], error=result.get("error"),
                    criteria=result["criteria"], score=result.get("score"), facts=result.get("facts", {}), second_opinion=result.get("second_opinion"), model=result.get("model", {}),
                    duration_ms=result.get("duration_ms", 0), cost_usd=result.get("cost_usd", 0.0), is_latest=True)
    s.add(ev); s.flush()
    for c in result.get("calls", []):
        s.add(LLMCallRow(evaluation_id=ev.id, conversation_id=d.conversation_id, criterion_id=c["criterion_id"], provider=c["provider"], model=c["model"], prompt_sha256=c["prompt_sha256"],
                         tokens_in=c["tokens_in"], tokens_out=c["tokens_out"], latency_ms=c["latency_ms"], cost_usd=c["cost_usd"], status=c["status"], response_text=c.get("response_text")))
    s.commit()
    return ev


def latest_evaluations(s: Session, group_id: str, checklist_version_id: int | None = None) -> list[Evaluation]:
    q = select(Evaluation).where(Evaluation.group_id == group_id, Evaluation.is_latest.is_(True))
    if checklist_version_id:
        q = q.where(Evaluation.checklist_version_id == checklist_version_id)
    return list(s.scalars(q))
