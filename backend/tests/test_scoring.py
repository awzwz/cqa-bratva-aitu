from decimal import Decimal

import pytest

from cqa.checklist_default import DEFAULT_CHECKLIST
from cqa.evaluator import checklist_defs
from cqa.export import build_results, validate_results
from cqa.scoring import compute_score, validate_answer

DEFS = checklist_defs(DEFAULT_CHECKLIST)


def test_appendix_example_85_38():
    # contact Да, discovery N/A, identification N/A, consultation 15, empathy Да, dialogue 7, closure Да, critical Нет
    answers = {"contact": True, "discovery": None, "identification": None, "consultation": 15, "empathy": True, "dialogue": 7, "closure": True, "critical": False}
    s = compute_score(DEFS, answers)
    assert s.total == Decimal("85.38")
    assert s.critical_flag is False
    assert sum(r.effective_weight for r in s.rows if r.applicable) == 100


def test_all_yes_is_100_and_scale_proportional():
    answers = {"contact": True, "discovery": True, "identification": True, "consultation": 20, "empathy": True, "dialogue": 10, "closure": True, "critical": False}
    assert compute_score(DEFS, answers).total == Decimal("100.00")
    answers["dialogue"] = 7
    assert compute_score(DEFS, answers).total == Decimal("95.50")  # 7/10*15 = 10.5 → 95.5


def test_half_up_rounding():
    # 50.625 → 50.63 (organisers confirmed half-up). Construct: applicable weights 80, earned 40.5
    answers = {"contact": True, "discovery": None, "identification": True, "consultation": 10, "empathy": False, "dialogue": 7, "closure": None, "critical": False}
    # weights: 10+20+20+15+15 = 80; points 10+20+10+0+10.5 = 50.5 → 63.125 → 63.13
    assert compute_score(DEFS, answers).total == Decimal("63.13")


def test_no_applicable_criteria_gives_none():
    answers = {"contact": False, "discovery": None, "identification": None, "consultation": None, "empathy": False, "dialogue": 0, "closure": None, "critical": True}
    s = compute_score(DEFS, answers)
    assert s.total == Decimal("0.00")  # contact/empathy/dialogue are applicable with 0 points
    only_na = {k: None for k in ("discovery", "identification", "consultation", "closure")}
    # remove non-N/A criteria entirely → missing, total None
    s2 = compute_score([d for d in DEFS if d.id in only_na], only_na)
    assert s2.total is None


def test_critical_flag_separate():
    # p1-ru-009 from DEV: discovery Да, identification Нет, consultation 10, empathy Нет, dialogue 7, closure Нет → 45.5/100
    answers = {"contact": True, "discovery": True, "identification": False, "consultation": 10, "empathy": False, "dialogue": 7, "closure": False, "critical": True}
    s = compute_score(DEFS, answers)
    assert s.critical_flag is True and s.total == Decimal("45.50")
    # same with discovery N/A: weights 85, points 30.5 → 35.88
    answers["discovery"] = None
    assert compute_score(DEFS, answers).total == Decimal("35.88")


def test_validate_answer_domains():
    by = {d.id: d for d in DEFS}
    assert validate_answer(by["consultation"], 15) == 15
    assert validate_answer(by["closure"], None) is None
    with pytest.raises(ValueError):
        validate_answer(by["contact"], None)  # N/A not allowed
    with pytest.raises(ValueError):
        validate_answer(by["consultation"], 12)
    with pytest.raises(ValueError):
        validate_answer(by["dialogue"], True)


def test_results_contract_roundtrip():
    ev = {"conversation_id": "p1-ru-001", "status": "ok",
          "criteria": {cid: {"value": v, "rationale": "r", "evidence_turns": [10]} for cid, v in
                       {"contact": True, "discovery": None, "identification": None, "consultation": 20, "empathy": True, "dialogue": 10, "closure": False, "critical": False}.items()},
          "score": {"final_score": 92.31, "critical_flag": False}}
    doc = build_results([ev, {"conversation_id": "p1-ru-002", "status": "error", "error": "boom"}], DEFS, modes={"external_api"}, model_name="openai/gpt-5.5")
    assert validate_results(doc, expected_ids=["p1-ru-001", "p1-ru-002"], expected_count=2, transcripts={"p1-ru-001": 12}) == []
    doc["results"][0]["criteria"][0]["value"] = None  # contact cannot be N/A
    assert any("out of domain" in p for p in validate_results(doc))
