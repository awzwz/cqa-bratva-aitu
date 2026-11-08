"""results.json — organisers' contract 1.0 (CQA_Student_Guide_Appendix_Results) + validator.

Only the model's values go into the file (appeal decisions live in the UI/DB); criterion ids
are the contract ids; evidence_turns are 1-based over the whole transcript; final_score is a
2-decimal number; critical_flag mirrors the critical criterion; failed dialogs are kept with
status "error" and score null (never a silent zero)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

from .config import settings
from .scoring import CriterionDef, answer_to_contract

CONTRACT_IDS = ["contact", "discovery", "identification", "consultation", "empathy", "dialogue", "closure", "critical"]

RESULTS_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object", "additionalProperties": False,
    "required": ["schema_version", "team_name", "model", "results"],
    "properties": {
        "schema_version": {"const": "1.0"},
        "team_name": {"type": "string", "minLength": 1},
        "model": {"type": "object", "required": ["mode", "name"], "additionalProperties": False,
                  "properties": {"mode": {"enum": ["local", "external_api", "hybrid"]}, "name": {"type": "string", "minLength": 1}}},
        "results": {"type": "array", "items": {"$ref": "#/$defs/result"}},
    },
    "$defs": {
        "criterion": {"type": "object", "additionalProperties": False, "required": ["criterion_id", "value", "rationale", "evidence_turns"],
                      "properties": {"criterion_id": {"enum": CONTRACT_IDS}, "value": {"type": ["boolean", "integer", "null"]},
                                     "rationale": {"type": "string"}, "evidence_turns": {"type": "array", "items": {"type": "integer", "minimum": 1}}}},
        "result": {"type": "object", "additionalProperties": False, "required": ["conversation_id", "status", "criteria", "score"],
                   "properties": {"conversation_id": {"type": "string", "minLength": 1}, "status": {"enum": ["ok", "error"]},
                                  "criteria": {"type": "array", "items": {"$ref": "#/$defs/criterion"}},
                                  "score": {"type": ["object", "null"], "additionalProperties": False, "required": ["final_score", "critical_flag"],
                                            "properties": {"final_score": {"type": ["number", "null"]}, "critical_flag": {"type": "boolean"}}},
                                  "error": {"type": "string"}}},
    },
}

VALUE_DOMAIN: dict[str, set] = {
    "contact": {True, False}, "discovery": {True, False, None}, "identification": {True, False, None}, "consultation": {0, 5, 10, 15, 20, None},
    "empathy": {True, False}, "dialogue": {0, 4, 7, 10}, "closure": {True, False, None}, "critical": {True, False},
}


def build_results(evaluations: list[dict], defs: list[CriterionDef], *, team_name: str | None = None, modes: set[str] | None = None, model_name: str) -> dict:
    mode = "hybrid" if modes and len(modes) > 1 else (next(iter(modes)) if modes else "external_api")
    by_id = {c.id: c for c in defs}
    results = []
    for ev in evaluations:
        if ev["status"] != "ok" or not ev.get("score"):
            results.append({"conversation_id": ev["conversation_id"], "status": "error", "criteria": [], "score": None, "error": ev.get("error") or "evaluation failed"})
            continue
        crit = []
        for cid in CONTRACT_IDS:
            c = by_id.get(cid); r = ev["criteria"].get(cid)
            if c is None or r is None:
                continue
            crit.append({"criterion_id": cid, "value": answer_to_contract(c, r["value"]), "rationale": r["rationale"], "evidence_turns": list(r["evidence_turns"])})
        results.append({"conversation_id": ev["conversation_id"], "status": "ok", "criteria": crit,
                        "score": {"final_score": ev["score"]["final_score"], "critical_flag": bool(ev["score"]["critical_flag"])}})
    return {"schema_version": "1.0", "team_name": team_name or settings.team_name, "model": {"mode": mode, "name": model_name}, "results": results}


def validate_results(doc: dict, *, expected_ids: list[str] | None = None, expected_count: int | None = None, transcripts: dict[str, int] | None = None) -> list[str]:
    """Schema + semantic checks. Returns a list of problems (empty = valid)."""
    problems: list[str] = []
    try:
        jsonschema.validate(doc, RESULTS_SCHEMA)
    except jsonschema.ValidationError as e:
        problems.append(f"schema: {e.message} at {'/'.join(str(p) for p in e.absolute_path)}")
    ids = [r["conversation_id"] for r in doc.get("results", [])]
    if len(ids) != len(set(ids)):
        problems.append("duplicate conversation_id")
    if expected_count is not None and len(ids) != expected_count:
        problems.append(f"expected {expected_count} results, got {len(ids)}")
    if expected_ids is not None and set(ids) != set(expected_ids):
        problems.append(f"ids differ from API: missing {sorted(set(expected_ids) - set(ids))}, extra {sorted(set(ids) - set(expected_ids))}")
    for r in doc.get("results", []):
        if r["status"] != "ok":
            continue
        cids = [c["criterion_id"] for c in r["criteria"]]
        if sorted(cids) != sorted(CONTRACT_IDS):
            problems.append(f"{r['conversation_id']}: criteria must be exactly the 8 contract ids once, got {cids}")
        for c in r["criteria"]:
            if c["value"] not in VALUE_DOMAIN.get(c["criterion_id"], set()) or (isinstance(c["value"], bool) and c["criterion_id"] in ("consultation", "dialogue")):
                problems.append(f"{r['conversation_id']}/{c['criterion_id']}: value {c['value']!r} out of domain")
            if not c["evidence_turns"]:
                problems.append(f"{r['conversation_id']}/{c['criterion_id']}: evidence_turns is empty")
            if transcripts and r["conversation_id"] in transcripts and any(t > transcripts[r["conversation_id"]] for t in c["evidence_turns"]):
                problems.append(f"{r['conversation_id']}/{c['criterion_id']}: evidence_turn beyond transcript length {transcripts[r['conversation_id']]}")
        crit = next((c for c in r["criteria"] if c["criterion_id"] == "critical"), None)
        if crit is not None and bool(crit["value"]) != bool(r["score"]["critical_flag"]):
            problems.append(f"{r['conversation_id']}: critical_flag != critical.value")
        fs = r["score"]["final_score"]
        if fs is not None and round(fs, 2) != fs:
            problems.append(f"{r['conversation_id']}: final_score has more than 2 decimals")
    return problems


def write_results(doc: dict, target: str) -> Path:
    path = settings.results_dir / target / "results.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
