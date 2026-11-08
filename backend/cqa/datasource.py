"""Organisers' data source: Power Automate HTTP trigger (signed URL) returning
{error, isSuccess, data:{dataset_group_id, total_records, records:[…]}}.

The signed query (`sig`, `sp`, `sv`) must be preserved — we never rebuild the URL from
parameters; `group_id` is added or replaced on the parsed query. Every raw response is
snapshotted to disk (sha256-named) so a run can be reproduced and the jury can audit it.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from .config import settings


def with_group_id(url: str, group_id: str) -> str:
    parts = urlsplit(url)
    q = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "group_id"]
    q.append(("group_id", group_id))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q, safe="%"), parts.fragment))


def fetch_dataset(group_id: str, url: str | None = None, *, timeout: float | None = None, retries: int | None = None) -> tuple[dict, Path]:
    """GET the dataset for `group_id`; returns (parsed json, snapshot path)."""
    base = url or settings.org_api_url
    if not base:
        raise RuntimeError("CQA_ORG_API_URL is not configured")
    target = with_group_id(base, group_id)
    timeout = timeout or settings.org_api_timeout
    retries = retries if retries is not None else settings.org_api_retries
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with httpx.Client(timeout=httpx.Timeout(timeout, connect=20.0), follow_redirects=True) as client:
                r = client.get(target, headers={"Accept": "application/json", "User-Agent": "cqa/1.0"})
            r.raise_for_status()
            raw = r.content
            data = json.loads(raw.decode("utf-8-sig"))
            if not data.get("isSuccess", True) or data.get("error"):
                raise RuntimeError(f"API error: {data.get('error')}")
            snap = snapshot(group_id, raw)
            return data, snap
        except Exception as e:  # noqa: BLE001 — retry on anything transient
            last = e
            if attempt < retries:
                time.sleep(min(2 ** attempt, 8))
    raise RuntimeError(f"dataset fetch failed after {retries + 1} attempts: {last}")


def snapshot(group_id: str, raw: bytes) -> Path:
    d = settings.data_dir / "snapshots"
    d.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256(raw).hexdigest()[:12]
    p = d / f"{group_id}_{time.strftime('%Y%m%dT%H%M%S')}_{sha}.json"
    p.write_bytes(raw)
    return p


def load_file(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if isinstance(data, list):  # a bare list of records
        return {"isSuccess": True, "error": "", "data": {"dataset_group_id": "FILE", "total_records": len(data), "records": data}}
    if "records" in data and "data" not in data:
        return {"isSuccess": True, "error": "", "data": data}
    return data


def records_of(data: dict) -> list[dict]:
    recs = (data.get("data") or {}).get("records") or []
    out = []
    for r in recs:
        if not r.get("conversation_id") or not isinstance(r.get("transcript"), list):
            continue
        out.append({
            "conversation_id": str(r["conversation_id"]),
            "channel": r.get("channel") or "agent chat",
            "language": (r.get("language") or "RU").upper(),
            "transcript": [{"timestamp": str(t.get("timestamp", "")), "speaker": str(t.get("speaker", "")).lower(), "text": str(t.get("text", ""))} for t in r["transcript"]],
            "audio_url": r.get("audio_url"),
        })
    return out
