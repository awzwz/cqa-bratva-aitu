"""Deterministic scoring engine — the LLM never computes points.

Rules (checklist, section «Порядок расчёта», confirmed by the organisers in chat):
1. N/A is allowed only where the criterion permits it; N/A is excluded from both sums.
2. Yes = full weight, No = 0; a scale step earns weight × step / top step.
3. total = Σ points / Σ weights of applicable criteria × 100.
4. Rounded to 2 decimals, ROUND_HALF_UP (50.625 → 50.63). No applicable weighted criteria → total is None.
5. `critical` (flag) never affects the total; it is reported separately.

All arithmetic is exact (Fraction) and only the final figure is quantised.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
from typing import Any

Answer = bool | int | float | None  # True/False, scale step, or None (= N/A)


@dataclass(frozen=True)
class CriterionDef:
    id: str
    code: str
    title: str
    section: str
    type: str  # "binary" | "scale" | "flag"
    weight: int
    allow_na: bool
    yes_rule: str = ""
    na_rule: str = ""
    scale: tuple[tuple[int, str], ...] = ()  # (step, description), descending
    guidance: str = ""
    order: int = 0

    @property
    def top_step(self) -> int:
        return max((s for s, _ in self.scale), default=1)

    def allowed_values(self) -> list[Any]:
        if self.type == "flag":
            return [True, False]
        if self.type == "binary":
            return [True, False] + ([None] if self.allow_na else [])
        return [s for s, _ in self.scale] + ([None] if self.allow_na else [])


@dataclass
class CriterionResult:
    criterion_id: str
    answer: Answer
    applicable: bool
    weight: int
    points: Fraction | None  # exact points earned (None for N/A / flag)
    effective_weight: Fraction | None  # weight after N/A redistribution (sums to 100)


@dataclass
class Score:
    total: Decimal | None
    critical_flag: bool
    rows: list[CriterionResult] = field(default_factory=list)
    sections: dict[str, dict[str, Any]] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)  # criteria without a verdict (model error) — distinct from N/A

    def total_float(self) -> float | None:
        return None if self.total is None else float(self.total)


def validate_answer(c: CriterionDef, answer: Any) -> Answer:
    """Normalise a raw answer to the criterion's domain or raise ValueError."""
    if answer is None:
        if c.type == "flag" or not c.allow_na:
            raise ValueError(f"{c.id}: N/A is not allowed")
        return None
    if c.type in ("binary", "flag"):
        if isinstance(answer, bool):
            return answer
        if isinstance(answer, str) and answer.strip().lower() in ("yes", "да", "true"):
            return True
        if isinstance(answer, str) and answer.strip().lower() in ("no", "нет", "false"):
            return False
        raise ValueError(f"{c.id}: expected yes/no, got {answer!r}")
    # scale
    if isinstance(answer, bool):
        raise ValueError(f"{c.id}: expected a scale step, got boolean")
    try:
        v = float(answer)
    except (TypeError, ValueError):
        raise ValueError(f"{c.id}: expected a scale step, got {answer!r}") from None
    for step, _ in c.scale:
        if float(step) == v:
            return step
    raise ValueError(f"{c.id}: {answer!r} is not a step of {[s for s, _ in c.scale]}")


def points_for(c: CriterionDef, answer: Answer) -> Fraction | None:
    if c.type == "flag" or answer is None:
        return None
    if c.type == "binary":
        return Fraction(c.weight) if answer else Fraction(0)
    return Fraction(c.weight) * Fraction(int(answer), c.top_step)


def q2(x: Fraction) -> Decimal:
    """Exact fraction → Decimal with 2 places, ROUND_HALF_UP (50.625 → 50.63)."""
    return (Decimal(x.numerator) / Decimal(x.denominator)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def compute_score(criteria: list[CriterionDef], answers: dict[str, Answer]) -> Score:
    rows: list[CriterionResult] = []
    missing: list[str] = []
    critical = False
    applicable: list[tuple[CriterionDef, Fraction]] = []
    for c in sorted(criteria, key=lambda k: k.order):
        if c.id not in answers:
            missing.append(c.id)
            rows.append(CriterionResult(c.id, None, False, c.weight, None, None))
            continue
        ans = answers[c.id]
        if c.type == "flag":
            critical = critical or bool(ans)
            rows.append(CriterionResult(c.id, ans, False, 0, None, None))
            continue
        pts = points_for(c, ans)
        if pts is None:
            rows.append(CriterionResult(c.id, None, False, c.weight, None, None))
        else:
            applicable.append((c, pts))
            rows.append(CriterionResult(c.id, ans, True, c.weight, pts, None))
    sum_w = sum((Fraction(c.weight) for c, _ in applicable), Fraction(0))
    total: Decimal | None = None
    if sum_w > 0 and not missing:
        earned = sum((p for _, p in applicable), Fraction(0))
        total = q2(earned / sum_w * 100)
        for r in rows:
            if r.applicable:
                r.effective_weight = Fraction(r.weight) * 100 / sum_w
    # sections: share of earned points within the section's applicable weight
    sections: dict[str, dict[str, Any]] = {}
    for c in criteria:
        sec = sections.setdefault(c.section, {"weight": Fraction(0), "points": Fraction(0), "applicable": 0})
        r = next(x for x in rows if x.criterion_id == c.id)
        if r.applicable and r.points is not None:
            sec["weight"] += Fraction(c.weight)
            sec["points"] += r.points
            sec["applicable"] += 1
    for name, sec in sections.items():
        sec["percent"] = float(q2(sec["points"] / sec["weight"] * 100)) if sec["weight"] > 0 else None
        sec["weight"] = float(sec["weight"])
        sec["points"] = float(sec["points"])
    return Score(total=total, critical_flag=critical, rows=rows, sections=sections, missing=missing)


def answer_to_contract(c: CriterionDef, answer: Answer) -> Any:
    """Value as the organisers' results.json contract expects: true/false/null or a numeric step."""
    if answer is None:
        return None
    if c.type in ("binary", "flag"):
        return bool(answer)
    return int(answer)
