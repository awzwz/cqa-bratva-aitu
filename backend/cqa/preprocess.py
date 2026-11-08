"""Transcript normalisation and facts computed by code (the model receives them as given).

Turn numbers are 1-based over the whole transcript (client, bot, system included) — exactly
the numbering the results contract uses for evidence_turns."""
from __future__ import annotations

import re
from datetime import datetime

SYSTEM_EVENTS = {
    "escalated": ["эскалация на оператора", "чат операторға жіберілді", "chat transferred to an agent", "агент присоединился", "переведен от агента"],
    "identity_verified": ["личность клиента подтверждена", "customer identity verified", "клиенттің жеке басы расталды"],
    "client_left": ["клиент покинул чат", "клиент завершил разговор", "соединение с клиентом прервано", "connection to customer lost", "клиентпен байланыс үзілді"],
    "operator_closed": ["оператор закрыл чат", "agent closed the chat", "оператор чатты жапты", "агент вышел из разговора"],
    "hold_start": ["клиент находится на удержании", "запись и транскрибирование приостановлены"],
    "hold_end": ["больше не находится на удержании", "запись и транскрибирование возобновлены"],
    "recording": ["запись и транскрибирование запущены", "жазу және транскрипция басталды", "transcription languages have been updated"],
}

GREETING_RE = re.compile(r"\b(здравствуй|добрый|доброе|привет|сәлем|сәлеметсіз|қайырлы|hello|hi\b|good (morning|afternoon|evening))", re.I)
NAME_RE = re.compile(r"(меня зовут|мен[яi]\s+зовут|я\s+[—-]?\s*[А-ЯЁӘҒҚҢӨҰҮІA-Z][а-яёәғқңөұүіa-z]+|мен\s+[А-ЯЁӘҒҚҢӨҰҮІ][а-яёәғқңөұүі]+(мын|мін|пын|пін|бын|бін)|i'?m\s+[A-Z][a-z]+|my name is|this is\s+[A-Z][a-z]+|\[имя скрыто\])", re.I)
FAREWELL_RE = re.compile(r"(до свидания|всего (доброго|хорошего)|хорошего (дня|вечера)|удачи|сау болыңыз|қош болыңыз|жақсы күн|goodbye|have a (nice|good|great) (day|evening)|bye\b)", re.I)
OFFER_RE = re.compile(r"(могу (ли )?(ещё|еще) (чем|чем-то|чем-нибудь) помочь|чем[- ]?(ещё|еще|то)[^.?!]{0,20}помочь|(есть|остались|появятся|возникнут) (ли )?(ещё |еще )?вопрос|если (появятся|будут|возникнут) вопрос|тағы (қандай )?(сұрақ|көмек)|басқа сұрақ|anything else|any (other|more) questions|if you have (any )?(more |other )?questions)", re.I)


def classify_event(text: str) -> str | None:
    t = text.lower()
    for name, needles in SYSTEM_EVENTS.items():
        if any(n in t for n in needles):
            return name
    return None


def parse_ts(ts: str) -> float | None:
    """Seconds from start: MM:SS for chats, ISO 8601 for calls (relative to first turn computed by caller)."""
    if not ts:
        return None
    m = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", ts.strip())
    if m:
        h, mi, s = (0, int(m.group(1)), int(m.group(2))) if m.group(3) is None else (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return h * 3600 + mi * 60 + s
    try:
        iso = re.sub(r"(\.\d{6})\d+", r"\1", ts.strip())  # trim >6 fractional digits for fromisoformat
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def normalize(record: dict) -> list[dict]:
    turns = []
    base = None
    for i, t in enumerate(record["transcript"], start=1):
        sec = parse_ts(t.get("timestamp", ""))
        if sec is not None and sec > 10 * 365 * 86400:  # absolute epoch → relative
            base = sec if base is None else base
            sec = sec - base
        turns.append({
            "n": i, "speaker": t.get("speaker", ""), "text": (t.get("text") or "").strip(), "timestamp": t.get("timestamp", ""),
            "t": sec, "event": classify_event(t.get("text", "")) if t.get("speaker") == "system" else None,
        })
    return turns


def compute_facts(record: dict, turns: list[dict]) -> dict:
    ops = [t for t in turns if t["speaker"] == "operator"]
    first_op = ops[0] if ops else None
    last_op = ops[-1] if ops else None
    events = [t for t in turns if t["speaker"] == "system" and t["event"]]
    identity_turns = [t["n"] for t in events if t["event"] == "identity_verified"]
    ending = None
    if last_op:
        tail = [t for t in events if t["n"] > last_op["n"]]
        if tail:
            ending = {"event": tail[-1]["event"], "turn": tail[-1]["n"]}
    client_before_op = [t["n"] for t in turns if t["speaker"] == "client" and (first_op is None or t["n"] < first_op["n"])]
    facts = {
        "channel": record.get("channel"), "language": record.get("language"), "turns_total": len(turns),
        "operator_turns": [t["n"] for t in ops], "first_operator_turn": first_op["n"] if first_op else None,
        "first_operator_text": first_op["text"] if first_op else None, "last_operator_turn": last_op["n"] if last_op else None,
        "greeting_in_first_operator_turn": bool(first_op and GREETING_RE.search(first_op["text"])),
        "name_in_first_operator_turn": bool(first_op and NAME_RE.search(first_op["text"])),
        "farewell_in_last_operator_turn": bool(last_op and FAREWELL_RE.search(last_op["text"])),
        "offer_or_summary_near_end": bool(any(OFFER_RE.search(t["text"]) for t in ops[-2:])) if ops else False,
        "identity_verified_turns": identity_turns,
        "system_events": [{"turn": t["n"], "event": t["event"]} for t in events],
        "ending": ending,  # how the dialog ended after the operator's last turn (client_left / operator_closed / None)
        "client_turns_before_operator": client_before_op,
        "first_operator_response_seconds": (first_op["t"] - next((t["t"] for t in turns if t["event"] == "escalated"), first_op["t"])) if first_op and first_op["t"] is not None else None,
    }
    return facts


def facts_to_text(f: dict) -> str:
    lines = [
        f"канал: {f['channel']}; язык: {f['language']}; реплик всего: {f['turns_total']}",
        f"реплики оператора: {f['operator_turns']} (первая #{f['first_operator_turn']}, последняя #{f['last_operator_turn']})",
        f"в первой реплике оператора: приветствие={'да' if f['greeting_in_first_operator_turn'] else 'нет'}, представление={'да' if f['name_in_first_operator_turn'] else 'нет'}",
        f"в конце: прощание={'да' if f['farewell_in_last_operator_turn'] else 'нет'}, итог/предложение помощи={'да' if f['offer_or_summary_near_end'] else 'нет'}",
        f"подтверждение личности (системное событие) в репликах: {f['identity_verified_turns'] or 'нет'}",
        f"системные события: {[(e['turn'], e['event']) for e in f['system_events']] or 'нет'}",
        f"как закончился диалог после последней реплики оператора: {f['ending'] or 'реплика оператора была последней / нет события'}",
        f"клиент написал до первого ответа оператора реплики: {f['client_turns_before_operator']}",
    ]
    return "\n".join(lines)


def render_transcript(turns: list[dict], *, bot_max: int = 240) -> str:
    who = {"client": "КЛИЕНТ", "operator": "ОПЕРАТОР", "bot": "БОТ", "system": "СИСТЕМА"}
    out = []
    for t in turns:
        text = t["text"].replace("\n", " ")
        if t["speaker"] == "bot" and len(text) > bot_max:
            text = text[:bot_max] + "…"
        ts = t["timestamp"][11:19] if len(t["timestamp"]) > 8 else t["timestamp"]
        out.append(f"#{t['n']} [{ts}] {who.get(t['speaker'], t['speaker'].upper())}: {text}")
    return "\n".join(out)


PII_RE = [
    (re.compile(r"\b\d{12}\b"), "[ИИН]"),
    (re.compile(r"\+?\d[\d\s\-()]{9,}\d"), "[телефон]"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), "[email]"),
    (re.compile(r"\b\d{16,20}\b"), "[номер карты/счёта]"),
]


def mask_pii(text: str) -> str:
    for rx, rep in PII_RE:
        text = rx.sub(rep, text)
    return text
