"""Tests for the fail-closed ledger health check."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from holdout_governance.health import check_ledger


def _payload(row: dict) -> str:
    return json.dumps(
        {k: v for k, v in row.items() if k not in ("prev_hash", "event_hash")},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _hash(prev: str, row: dict) -> str:
    return hashlib.sha256(f"{prev}\x00{_payload(row)}".encode("utf-8")).hexdigest()


def _row(event: str, record_id: str, recorded_at: str, prev: str) -> dict:
    row = {
        "schema_version": "falsification_ledger.prediction_event.v1",
        "event": event,
        "record_id": record_id,
        "recorded_at": recorded_at,
        "prev_hash": prev or None,
    }
    row["event_hash"] = _hash(prev, row)
    return row


def _write(tmp: Path, rows: list[dict]) -> Path:
    path = tmp / "ledger.jsonl"
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    return path


def test_healthy_chain_passes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        first = _row("register", "id-1", "2026-09-01T10:00:00+08:00", "")
        second = _row("conclude", "id-2", "2026-09-02T10:00:00+08:00", first["event_hash"])
        path = _write(Path(tmp), [first, second])
        report = check_ledger(path)
        assert report["ok"] is True
        assert report["lines"] == 2
        assert report["issues"] == []


def test_tampered_row_breaks_chain() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        first = _row("register", "id-1", "2026-09-01T10:00:00+08:00", "")
        second = _row("conclude", "id-2", "2026-09-02T10:00:00+08:00", first["event_hash"])
        second["expected_verdict"] = "tampered"  # 内容被改但哈希未更新
        path = _write(Path(tmp), [first, second])
        report = check_ledger(path)
        assert report["ok"] is False
        reasons = {i["reason"] for i in report["issues"]}
        assert "event_hash_mismatch" in reasons


def test_duplicate_record_id_and_bad_json_fail() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        row = _row("register", "dup", "2026-09-01T10:00:00+08:00", "")
        path = tmp_path = Path(tmp) / "ledger.jsonl"
        path.write_text(
            json.dumps(row, ensure_ascii=False)
            + "\n{not-json\n"
            + json.dumps(row, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        report = check_ledger(path)
        assert report["ok"] is False
        reasons = {i["reason"] for i in report["issues"]}
        assert reasons == {"bad_json", "duplicate_record_id"}


def test_legacy_rows_reanchored() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        legacy = {"schema_version": "v0", "record_id": "old", "recorded_at": "2026-01-01T00:00:00+08:00"}
        modern = _row("register", "id-2", "2026-09-02T10:00:00+08:00", _hash("", legacy))
        path = _write(Path(tmp), [legacy, modern])
        report = check_ledger(path)
        assert report["ok"] is True
        assert report["legacy_reanchored"] == 1


def test_unreadable_ledger_fails_closed() -> None:
    report = check_ledger(Path("/nonexistent/ledger.jsonl"))
    assert report["ok"] is False
    assert any("unreadable" in str(b) for b in report["blockers"])
