"""LLM gateway: pluggable providers behind one interface, a fallback chain, a response cache
and a cost ledger. Any OpenAI-compatible endpoint (OpenAI, DeepSeek, Gemini's OpenAI
endpoint, Ollama, LM Studio, vLLM, OpenRouter) is one provider class; Anthropic is another.

Every call returns an LLMCall record (provider, model, tokens, latency, cost, raw text)
that is persisted — this is the audit trail proving dialogs are analysed live."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from ..config import settings

log = logging.getLogger("cqa.llm")


class LLMError(RuntimeError):
    pass


# USD per 1M tokens (input, output). Used for the cost ledger; unknown models → 0.
PRICES: dict[str, tuple[float, float]] = {
    "gpt-5.5": (5.0, 30.0), "gpt-5.4-mini": (0.75, 4.5), "gpt-5": (1.25, 10.0), "gpt-4.1": (2.0, 8.0), "gpt-4.1-mini": (0.4, 1.6), "gpt-4o": (2.5, 10.0), "gpt-4o-mini": (0.15, 0.6),
    "claude-sonnet-5-5": (3.0, 15.0), "claude-opus-5-5": (5.0, 25.0), "claude-haiku-5-5": (1.0, 5.0),
    "gemini-3.8-flash": (0.3, 2.5), "gemini-2.5-flash": (0.3, 2.5), "deepseek-chat": (0.27, 1.1), "deepseek-v3.4": (0.27, 1.1),
}


def price_for(model: str, tokens_in: int, tokens_out: int) -> float:
    for k, (pi, po) in sorted(PRICES.items(), key=lambda kv: -len(kv[0])):  # longest prefix wins: gpt-5.4-mini before gpt-5
        if model.startswith(k):
            return tokens_in / 1e6 * pi + tokens_out / 1e6 * po
    return 0.0


@dataclass
class LLMCall:
    provider: str
    model: str
    prompt_sha256: str
    response_text: str
    parsed: dict | None
    tokens_in: int
    tokens_out: int
    latency_ms: int
    cost_usd: float
    status: str  # ok | repair | error | cache
    error: str | None = None
    meta: dict = field(default_factory=dict)


def extract_json(text: str) -> dict:
    t = text.strip()
    t = re.sub(r"^<think>.*?</think>", "", t, flags=re.S).strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t).rstrip("`").strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, flags=re.S)
        if not m:
            raise
        return json.loads(m.group(0))


class Provider:
    id: str
    model: str
    mode: str  # external_api | local

    def complete_json(self, system: str, user: str, schema: dict, *, max_tokens: int = 900) -> tuple[str, int, int]:
        """Return (text, tokens_in, tokens_out). Must try to honour `schema`."""
        raise NotImplementedError

    def health(self) -> bool:
        return True


class OpenAICompatProvider(Provider):
    """OpenAI SDK against any compatible base_url. Uses response_format json_schema when the
    server supports it and falls back to json_object / plain text otherwise."""

    def __init__(self, id: str, model: str, api_key: str | None, base_url: str | None, mode: str, strict_schema: bool = True):
        from openai import OpenAI
        self.id, self.model, self.mode, self.strict = id, model, mode, strict_schema
        self.client = OpenAI(api_key=api_key or "local", base_url=base_url, timeout=settings.llm_timeout, max_retries=1)
        self._schema_ok = True

    def complete_json(self, system, user, schema, *, max_tokens=900):
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        kwargs: dict[str, Any] = {"model": self.model, "messages": msgs}
        if not self.model.startswith(("gpt-5", "o1", "o3", "o4")):
            kwargs["temperature"] = 0
        if self.model.startswith(("gpt-5", "o1", "o3", "o4")):
            kwargs["max_completion_tokens"] = max_tokens * 4  # reasoning tokens count against the limit
            if self.id == "openai":
                kwargs["reasoning_effort"] = settings.openai_reasoning_effort
        else:
            kwargs["max_tokens"] = max_tokens
        if self._schema_ok:
            kwargs["response_format"] = {"type": "json_schema", "json_schema": {"name": "verdict", "schema": schema, "strict": self.strict}}
        try:
            r = self.client.chat.completions.create(**kwargs)
        except Exception as e:  # noqa: BLE001 — servers without json_schema support
            if "response_format" in kwargs and ("response_format" in str(e) or "json_schema" in str(e) or "400" in str(e)):
                self._schema_ok = False
                kwargs["response_format"] = {"type": "json_object"}
                try:
                    r = self.client.chat.completions.create(**kwargs)
                except Exception as e2:  # noqa: BLE001
                    kwargs.pop("response_format", None)
                    r = self.client.chat.completions.create(**kwargs)
            else:
                raise
        text = r.choices[0].message.content or ""
        u = getattr(r, "usage", None)
        return text, int(getattr(u, "prompt_tokens", 0) or 0), int(getattr(u, "completion_tokens", 0) or 0)

    def health(self) -> bool:
        try:
            self.client.models.list()
            return True
        except Exception:  # noqa: BLE001
            return False


class AnthropicProvider(Provider):
    def __init__(self, id: str, model: str, api_key: str):
        import anthropic
        self.id, self.model, self.mode = id, model, "external_api"
        self.client = anthropic.Anthropic(api_key=api_key, timeout=settings.llm_timeout, max_retries=1)

    def complete_json(self, system, user, schema, *, max_tokens=900):
        tool = {"name": "verdict", "description": "Return the structured verdict.", "input_schema": schema}
        r = self.client.messages.create(model=self.model, max_tokens=max_tokens, system=system, messages=[{"role": "user", "content": user}], tools=[tool], tool_choice={"type": "tool", "name": "verdict"})
        for block in r.content:
            if getattr(block, "type", "") == "tool_use":
                return json.dumps(block.input, ensure_ascii=False), r.usage.input_tokens, r.usage.output_tokens
        text = "".join(getattr(b, "text", "") for b in r.content)
        return text, r.usage.input_tokens, r.usage.output_tokens


class RulesProvider(Provider):
    """Offline provider: answers from the code-computed facts only (greeting/name, farewell/offer,
    identity events). Used for smoke tests, CI and as the last-resort fallback when every model
    is unreachable — it never invents text, every rationale names the fact it used."""

    id, model, mode = "rules", "rules-v1", "local"

    def complete_json(self, system, user, schema, *, max_tokens=900):
        f = {}
        for line in user.splitlines():
            if ":" in line and ("=" in line or "реплик" in line or "подтверждение" in line or "закончился" in line):
                f[line.split(":", 1)[0].strip()] = line.split(":", 1)[1].strip()
        crit = re.search(r"КРИТЕРИЙ (\d\d)", user).group(1) if re.search(r"КРИТЕРИЙ (\d\d)", user) else "00"
        first_op = int(m.group(1)) if (m := re.search(r"первая #(\d+)", user)) else 1
        last_op = int(m.group(1)) if (m := re.search(r"последняя #(\d+)", user)) else first_op
        greet = "приветствие=да" in user and "представление=да" in user
        farewell = "прощание=да" in user; offer = "итог/предложение помощи=да" in user
        identity = re.search(r"подтверждение личности \(системное событие\) в репликах: \[(\d+)", user)
        ended_by_client = "client_left" in user
        value: Any; ev = [first_op]; why = ""
        if crit == "01":
            value, why = greet, f"Правило: приветствие {'и имя есть' if greet else 'или имя отсутствует'} в первой реплике оператора #{first_op}."
        elif crit == "02":
            value, why = None, "Правило: данных клиента хватало (режим без модели)."
        elif crit == "03":
            value = True if identity else None
            ev = [int(identity.group(1))] if identity else [first_op]
            why = "Правило: есть системное событие подтверждения личности." if identity else "Правило: событие идентификации отсутствует; считаем запрос общим (режим без модели)."
        elif crit == "04":
            value, ev, why = 15, [last_op], "Правило: консультация не проверяется без модели, выставлена средняя ступень."
        elif crit == "05":
            value, why = True, "Правило: признаков грубости нет (режим без модели)."
        elif crit == "06":
            value, ev, why = 7, [last_op], "Правило: ведение диалога не проверяется без модели, выставлена ступень 7."
        elif crit == "07":
            value = None if ended_by_client else (farewell and offer)
            ev = [last_op]
            why = "Правило: чат оборвался клиентом — N/A." if ended_by_client else f"Правило: прощание={'да' if farewell else 'нет'}, итог/предложение помощи={'да' if offer else 'нет'} в последних репликах оператора."
        else:
            value, ev, why = False, [last_op], "Правило: грубые нарушения без модели не детектируются."
        return json.dumps({"value": value, "evidence_turns": ev, "rationale": why, "na_reason": "" if value is not None else why, "expected_turn": None, "confidence": 0.3}, ensure_ascii=False), 0, 0


def build_router() -> "LLMRouter":
    providers: list[Provider] = []
    for pid in [p.strip() for p in settings.provider_chain.split(",") if p.strip()]:
        p = make_provider(pid)
        if p:
            providers.append(p)
    if not providers:
        raise LLMError("no LLM provider configured: set CQA_OPENAI_API_KEY (or another provider) in .env")
    second = make_provider(settings.second_opinion_provider) if settings.second_opinion_provider else None
    return LLMRouter(providers, second_opinion=second)


def make_provider(pid: str) -> Provider | None:
    s = settings
    if pid == "openai" and s.openai_api_key:
        return OpenAICompatProvider("openai", s.openai_model, s.openai_api_key, s.openai_base_url, "external_api")
    if pid == "anthropic" and s.anthropic_api_key:
        return AnthropicProvider("anthropic", s.anthropic_model, s.anthropic_api_key)
    if pid == "gemini" and s.gemini_api_key:
        return OpenAICompatProvider("gemini", s.gemini_model, s.gemini_api_key, s.gemini_base_url, "external_api", strict_schema=False)
    if pid == "deepseek" and s.deepseek_api_key:
        return OpenAICompatProvider("deepseek", s.deepseek_model, s.deepseek_api_key, s.deepseek_base_url, "external_api", strict_schema=False)
    if pid == "ollama":
        return OpenAICompatProvider("ollama", s.ollama_model, None, s.ollama_base_url, "local", strict_schema=False)
    if pid == "lmstudio":
        return OpenAICompatProvider("lmstudio", s.lmstudio_model, None, s.lmstudio_base_url, "local", strict_schema=False)
    if pid == "rules":
        return RulesProvider()
    log.warning("provider %s skipped (no key / unknown)", pid)
    return None


class LLMRouter:
    def __init__(self, providers: list[Provider], second_opinion: Provider | None = None):
        self.providers = providers
        self.second_opinion = second_opinion
        self.cache: dict[str, LLMCall] = {}
        self.spent_usd = 0.0
        self._lock = threading.Lock()

    @property
    def primary(self) -> Provider:
        return self.providers[0]

    def modes_used(self) -> set[str]:
        return {p.mode for p in self.providers} | ({self.second_opinion.mode} if self.second_opinion else set())

    def call(self, system: str, user: str, schema: dict, *, validator=None, max_tokens: int = 900, provider: Provider | None = None) -> LLMCall:
        """Call the chain (or one provider) with validation + one repair round per provider.
        `validator(parsed) -> parsed` raises ValueError when the model's answer is out of domain."""
        key = hashlib.sha256((system + "\n\x00" + user + "\x00" + json.dumps(schema, sort_keys=True)).encode()).hexdigest()
        with self._lock:
            if key in self.cache and provider is None:
                c = self.cache[key]
                return LLMCall(c.provider, c.model, c.prompt_sha256, c.response_text, c.parsed, 0, 0, 0, 0.0, "cache", meta={"cached": True})
            if self.spent_usd > settings.llm_budget_usd:
                raise LLMError(f"budget exceeded: ${self.spent_usd:.2f} > ${settings.llm_budget_usd:.2f}")
        chain = [provider] if provider else self.providers
        errors = []
        for p in chain:
            attempt_user = user
            for attempt in range(2):
                t0 = time.time()
                try:
                    text, tin, tout = p.complete_json(system, attempt_user, schema, max_tokens=max_tokens)
                    parsed = extract_json(text)
                    if validator:
                        parsed = validator(parsed)
                    cost = price_for(p.model, tin, tout)
                    rec = LLMCall(p.id, p.model, key[:16], text, parsed, tin, tout, int((time.time() - t0) * 1000), cost, "ok" if attempt == 0 else "repair")
                    with self._lock:
                        self.spent_usd += cost
                        if provider is None:
                            self.cache[key] = rec
                    return rec
                except (ValueError, json.JSONDecodeError) as e:  # bad JSON / out-of-domain → repair once
                    errors.append(f"{p.id}: invalid answer: {e}")
                    attempt_user = user + f"\n\nПредыдущий ответ был отклонён: {e}. Верни корректный JSON строго по схеме и допустимым значениям."
                    continue
                except Exception as e:  # noqa: BLE001 — transport/provider error → next provider
                    errors.append(f"{p.id}: {type(e).__name__}: {str(e)[:200]}")
                    log.warning("provider %s failed: %s", p.id, e)
                    break
        raise LLMError("; ".join(errors) or "all providers failed")
