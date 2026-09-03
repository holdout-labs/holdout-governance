"""Ledger health checks (``gov health``).

Companion to the demo ledger (``examples/gov-demo/ledger/ledger.jsonl``,
falsification-ledger event format): parse every line, check required fields,
duplicate record ids, event-hash self-consistency and prev-hash chain
continuity, and recorded-at ordering.  Fail-closed: any issue fails the run.

The hash semantics mirror the falsification-ledger contract:
``event_hash = sha256(prev_hash || 0x00 || canonical-payload)`` where the
canonical payload excludes ``prev_hash`` and ``event_hash`` themselves.
Rows written before hashes existed are re-anchored (their recomputed hash is
the chain head for the next row) and reported as ``legacy_reanchored``.

Added 2026-09 as the dogfood backfill of the internal governance ledger
health check (bad rows / duplicate ids detected fail-closed before use).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "holdout_governance.ledger_health.v1"
REQUIRED_FIELDS = ("schema_version", "record_id", "recorded_at")


def _canonical_payload(row: dict[str, Any]) -> str:
    payload = {
        key: value for key, value in row.items() if key not in ("prev_hash", "event_hash")
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _event_hash(prev_hash: str, payload: str) -> str:
    return hashlib.sha256(f"{prev_hash}\x00{payload}".encode("utf-8")).hexdigest()


def check_ledger(path: str | Path) -> dict[str, Any]:
    """Verify one ledger JSONL file; return the health report (pure IO)."""
    ledger = Path(path)
    issues: list[dict[str, Any]] = []
    rows: list[tuple[int, dict[str, Any]]] = []
    try:
        text = ledger.read_text(encoding="utf-8-sig")
    except OSError as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "path": str(ledger),
            "lines": 0,
            "ok": False,
            "blockers": [f"unreadable: {exc}"],
            "issues": [],
            "note": "cannot read ledger - fail-closed",
        }
    for line_no, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            issues.append({"line": line_no, "reason": "bad_json", "detail": str(exc)[:120]})
            continue
        if not isinstance(row, dict):
            issues.append({"line": line_no, "reason": "not_object"})
            continue
        missing = [field for field in REQUIRED_FIELDS if field not in row]
        if missing:
            issues.append({"line": line_no, "reason": "missing_fields", "fields": missing})
            continue
        rows.append((line_no, row))

    seen_ids: dict[str, int] = {}
    prev_effective: str | None = None
    prev_stamp: str | None = None
    legacy_reanchored = 0
    for line_no, row in rows:
        record_id = str(row.get("record_id") or "")
        if record_id in seen_ids:
            issues.append(
                {"line": line_no, "reason": "duplicate_record_id",
                 "record_id": record_id, "first_line": seen_ids[record_id]}
            )
        else:
            seen_ids[record_id] = line_no

        stamp = str(row.get("recorded_at") or "")
        if prev_stamp is not None and stamp < prev_stamp:
            issues.append(
                {"line": line_no, "reason": "recorded_at_out_of_order",
                 "recorded_at": stamp, "previous": prev_stamp}
            )
        if stamp:
            prev_stamp = stamp

        recorded_prev = str(row.get("prev_hash") or "") if row.get("prev_hash") is not None else ""
        has_chain_fields = "event_hash" in row or "prev_hash" in row
        payload = _canonical_payload(row)
        if not has_chain_fields:
            legacy_reanchored += 1
            prev_effective = _event_hash("", payload)
            continue
        if recorded_prev and prev_effective is not None and recorded_prev != prev_effective:
            issues.append(
                {"line": line_no, "reason": "prev_hash_mismatch",
                 "expected": prev_effective, "recorded": recorded_prev}
            )
        expected = _event_hash(recorded_prev, payload)
        if "event_hash" in row and str(row.get("event_hash") or "") != expected:
            issues.append(
                {"line": line_no, "reason": "event_hash_mismatch",
                 "expected": expected, "recorded": str(row.get("event_hash"))}
            )
        prev_effective = str(row.get("event_hash") or expected)

    return {
        "schema_version": SCHEMA_VERSION,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "path": str(ledger),
        "lines": len(rows),
        "legacy_reanchored": legacy_reanchored,
        "ok": not issues,
        "issues": issues,
        "note": (
            "fail-closed ledger health: bad json / missing fields / duplicate "
            "record ids / hash-chain breaks / recorded_at out of order all fail."
        ),
    }
