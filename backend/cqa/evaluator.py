"""Per-criterion evaluation driven entirely by the checklist configuration.

For each criterion the model gets: general rules, code-computed facts, the numbered
transcript and the criterion card (type, allowed values, Yes/N/A rules, guidance).
It returns {value, rationale, evidence_turns, na_reason, expected_turn, confidence}.
Code validates the value domain and the evidence (turn exists; for operator-side
criteria at least one cited turn belongs to the operator or is a system event) and
then computes the score. One failed criterion marks the evaluation `error` — never a
silent zero (contract: status=error)."""
from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .checklist_default import DEFAULT_CHECKLIST
from .config import settings
from .llm.router import LLMCall, LLMError, LLMRouter
from .preprocess import compute_facts, facts_to_text, mask_pii, normalize, render_transcript
from .scoring import CriterionDef, compute_score, validate_answer

log = logging.getLogger("cqa.eval")

SYSTEM_PROMPT = """Ты — эксперт отдела контроля качества контакт-центра брокера Freedom Broker (Казахстан).
Ты оцениваешь работу ОПЕРАТОРА в диалоге с клиентом строго по ОДНОМУ критерию чек-листа за раз.
Диалоги бывают на русском, казахском и английском — ты свободно понимаешь все три. Обоснование пиши по-русски, цитаты оставляй на языке оригинала.

ОБЩИЕ ПРАВИЛА ЧЕК-ЛИСТА:
{general_rules}

ФОРМАТ ОТВЕТА — строго JSON по схеме:
- "value": вердикт, только одно из допустимых значений критерия.
- "evidence_turns": номера реплик (1–3), подтверждающие вывод; для пропущенного действия — реплика, где оно ожидалось; для N/A — реплика или системное событие, подтверждающее неприменимость.
- "rationale": 1–2 предложения по-русски в стиле: «Завершение — Нет. После ответа оператор закрыл чат без прощания. Основание — последняя реплика оператора и сообщение о закрытии чата».
- "na_reason": причина N/A (пустая строка, если не N/A). "expected_turn": номер реплики, где ожидалось пропущенное действие (null, если не применимо). "confidence": 0–1.
Оценивай только то, что есть в транскрипте. Не выдумывай реплик и фактов. «Нет» ставь только при явном нарушении условия, подтверждённом конкретной репликой."""


def checklist_defs(checklist: dict) -> list[CriterionDef]:
    out = []
    for i, c in enumerate(checklist["criteria"]):
        out.append(CriterionDef(
            id=c["id"], code=c.get("code", str(i + 1)), title=c["title"], section=c.get("section", ""), type=c["type"],
            weight=int(c.get("weight", 0)), allow_na=bool(c.get("allow_na", False)), yes_rule=c.get("yes_rule", ""), na_rule=c.get("na_rule", ""),
            scale=tuple((int(s[0]), str(s[1])) for s in c.get("scale", [])), guidance=c.get("guidance", ""), order=i,
        ))
    return out


def value_schema(c: CriterionDef) -> dict:
    if c.type == "scale":
        vals: list[Any] = [s for s, _ in c.scale]
        sch: dict = {"type": ["integer", "null"] if c.allow_na else "integer", "enum": vals + ([None] if c.allow_na else [])}
    else:
        sch = {"type": ["boolean", "null"] if (c.allow_na and c.type != "flag") else "boolean"}
    return sch


def response_schema(c: CriterionDef) -> dict:
    return {
        "type": "object", "additionalProperties": False,
        "properties": {
            "value": value_schema(c),
            "evidence_turns": {"type": "array", "items": {"type": "integer"}, "minItems": 1, "maxItems": 4},
            "rationale": {"type": "string"},
            "na_reason": {"type": "string"},
            "expected_turn": {"type": ["integer", "null"]},
            "confidence": {"type": "number"},
        },
        "required": ["value", "evidence_turns", "rationale", "na_reason", "expected_turn", "confidence"],
    }


def criterion_card(c: CriterionDef) -> str:
    lines = [f"КРИТЕРИЙ {c.code} «{c.title}» (секция: {c.section}; вес {c.weight})"]
    if c.type == "flag":
        lines += ["Тип: флаг нарушения, true = нарушение выявлено, false = нет (баллы не считаются).", f"Нарушение: {c.yes_rule}"]
    elif c.type == "binary":
        lines += ["Тип: Да/Нет" + (" / N/A (null)" if c.allow_na else ""), f"Да (true) — {c.yes_rule}", "Нет (false) — действие было нужно, но оператор его пропустил или выполнил неправильно."]
    else:
        lines += ["Тип: шкала, выбери ровно одну ступень (число):"] + [f"  {s} — {d}" for s, d in c.scale]
    if c.allow_na and c.type != "flag":
        lines.append(f"N/A (null) — {c.na_rule} Ставь N/A только если это условие выполнено.")
    else:
        lines.append("N/A для этого критерия не допускается.")
    if c.guidance:
        lines.append(f"Пояснения: {c.guidance}")
    return "\n".join(lines)


def make_validator(c: CriterionDef, n_turns: int, operator_turns: set[int], system_turns: set[int]):
    def validate(parsed: dict) -> dict:
        if not isinstance(parsed, dict):
            raise ValueError("ответ не объект")
        value = validate_answer(c, parsed.get("value"))
        ev = parsed.get("evidence_turns") or []
        if not isinstance(ev, list):
            raise ValueError("evidence_turns должен быть списком")
        ev = [int(x) for x in ev if isinstance(x, (int, float)) and not isinstance(x, bool)]
        ev = [x for x in dict.fromkeys(ev) if 1 <= x <= n_turns]
        if not ev:
            raise ValueError(f"evidence_turns пуст или вне диапазона 1..{n_turns}")
        if c.type != "flag" and value is not None and not any(x in operator_turns or x in system_turns for x in ev):
            raise ValueError("ни одна реплика-доказательство не принадлежит оператору или системе")
        exp = parsed.get("expected_turn")
        exp = int(exp) if isinstance(exp, (int, float)) and not isinstance(exp, bool) and 1 <= int(exp) <= n_turns else None
        conf = parsed.get("confidence")
        conf = float(conf) if isinstance(conf, (int, float)) and not isinstance(conf, bool) else 0.5
        return {"value": value, "evidence_turns": ev[:4], "rationale": str(parsed.get("rationale", "")).strip()[:600],
                "na_reason": str(parsed.get("na_reason", "")).strip()[:300], "expected_turn": exp, "confidence": max(0.0, min(1.0, conf))}
    return validate


def evaluate_dialog(record: dict, checklist: dict, router: LLMRouter, *, parallel: int | None = None, second_opinion: bool = False) -> dict:
    """Evaluate one dialog. Returns a dict ready for persistence and for the results contract."""
    t0 = time.time()
    defs = checklist_defs(checklist)
    turns = normalize(record)
    if settings.mask_pii:
        for t in turns:
            t["text"] = mask_pii(t["text"])
    facts = compute_facts(record, turns)
    system = SYSTEM_PROMPT.format(general_rules=checklist.get("general_rules", DEFAULT_CHECKLIST["general_rules"]))
    head = (f"ДИАЛОГ {record['conversation_id']} · канал: {record.get('channel')} · язык: {record.get('language')}\n"
            + ("Это расшифровка телефонного звонка (автоматическое распознавание речи): возможны ошибки распознавания и маскированные данные — оценивай смысл.\n" if (record.get("channel") or "").startswith("voice") else "")
            + f"\nФАКТЫ, ВЫЧИСЛЕННЫЕ СИСТЕМОЙ:\n{facts_to_text(facts)}\n\nТРАНСКРИПТ (номер реплики, время, роль, текст; нумерация с 1 по всем репликам):\n{render_transcript(turns)}")
    op_turns = {t["n"] for t in turns if t["speaker"] == "operator"}
    sys_turns = {t["n"] for t in turns if t["speaker"] == "system"}

    def run_one(c: CriterionDef) -> tuple[str, dict | None, LLMCall | None, str | None]:
        user = f"{head}\n\n==========\n{criterion_card(c)}\n\nОцени критерий {c.code} и верни JSON."
        try:
            call = router.call(system, user, response_schema(c), validator=make_validator(c, len(turns), op_turns, sys_turns))
            return c.id, call.parsed, call, None
        except LLMError as e:
            return c.id, None, None, str(e)

    with ThreadPoolExecutor(max_workers=parallel or settings.llm_parallel) as ex:
        outcomes = list(ex.map(run_one, defs))

    criteria_out: dict[str, dict] = {}
    calls: list[dict] = []
    errors: list[str] = []
    for cid, parsed, call, err in outcomes:
        if call:
            calls.append({"criterion_id": cid, "provider": call.provider, "model": call.model, "prompt_sha256": call.prompt_sha256, "tokens_in": call.tokens_in, "tokens_out": call.tokens_out,
                          "latency_ms": call.latency_ms, "cost_usd": call.cost_usd, "status": call.status, "response_text": call.response_text})
        if parsed is None:
            errors.append(f"{cid}: {err}")
            continue
        criteria_out[cid] = parsed
    answers = {cid: v["value"] for cid, v in criteria_out.items()}
    score = compute_score(defs, answers) if not errors else None

    second: dict[str, Any] | None = None
    if second_opinion and router.second_opinion and not errors:
        second = {}
        for c in defs:
            user = f"{head}\n\n==========\n{criterion_card(c)}\n\nОцени критерий {c.code} и верни JSON."
            try:
                call = router.call(system, user, response_schema(c), validator=make_validator(c, len(turns), op_turns, sys_turns), provider=router.second_opinion)
                second[c.id] = {"value": call.parsed["value"], "agrees": call.parsed["value"] == answers.get(c.id), "model": call.model}
                calls.append({"criterion_id": c.id, "provider": call.provider, "model": call.model, "prompt_sha256": call.prompt_sha256, "tokens_in": call.tokens_in, "tokens_out": call.tokens_out,
                              "latency_ms": call.latency_ms, "cost_usd": call.cost_usd, "status": "second_opinion", "response_text": call.response_text})
            except LLMError as e:
                second[c.id] = {"error": str(e)}

    return {
        "conversation_id": record["conversation_id"], "status": "ok" if not errors else "error", "error": "; ".join(errors) if errors else None,
        "criteria": criteria_out, "score": None if score is None else {"final_score": score.total_float(), "critical_flag": score.critical_flag, "sections": score.sections,
                                                                         "rows": [{"criterion_id": r.criterion_id, "applicable": r.applicable, "weight": r.weight,
                                                                                   "points": None if r.points is None else float(r.points), "effective_weight": None if r.effective_weight is None else float(r.effective_weight)} for r in score.rows]},
        "facts": facts, "turns": turns, "calls": calls, "second_opinion": second,
        "model": {"provider": router.primary.id, "name": router.primary.model, "mode": router.primary.mode},
        "duration_ms": int((time.time() - t0) * 1000), "cost_usd": round(sum(c["cost_usd"] for c in calls), 6),
        "checklist_key": checklist.get("key"), "checklist_version": checklist.get("version", 1),
    }
