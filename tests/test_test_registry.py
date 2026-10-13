"""Shared authority, overlap, replay and crash behavior without market data."""
from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from holdout_governance import test_registry as reg


def dataset(samples=None):
    return reg.register("custodian-feed", samples or [("A", "2025-01-01", "2025-01-02")])


def claim(ref, request="request", study="study"):
    return reg.claim(ref, request, study, "frozen-hash", "operator")


def test_identity_ignores_row_order_and_duplicate_serialization():
    rows = [("A", "2025-01-01", "2025-01-02"), ("B", "2025-01-03", "2025-01-04")]
    first = dataset(rows)
    second = dataset(list(reversed(rows)) + rows)
    assert first["dataset_id"] == second["dataset_id"]
    assert claim(first)["granted"]
    assert claim(second, "new-folder", "renamed-study")["status"] == "denied"


@pytest.mark.parametrize("rows", [
    [("A", "2025-01-02", "2025-01-09")],  # shared boundary
    [("A", "2024-12-01", "2025-01-15")],  # containing interval
    [("A", "2025-01-01", "2025-01-01")],  # changed target horizon
])
def test_overlap_is_denied(rows):
    assert claim(dataset())["granted"]
    second = dataset(rows)
    assert not reg.status(second)["available"]
    assert claim(second, "second")["status"] == "denied"


def test_new_observations_are_allowed():
    assert claim(dataset())["granted"]
    assert claim(dataset([("A", "2025-01-03", "2025-01-04")]), "next")["granted"]
    assert claim(dataset([("B", "2025-01-01", "2025-01-02")]), "other-asset")["granted"]


def test_atomic_cross_study_claim_only_one_wins():
    ref = dataset()
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(lambda n: claim(ref, f"r{n}", f"study{n}"), range(2)))
    assert sum(r["granted"] for r in receipts) == 1
    assert sorted(r["status"] for r in receipts) == ["denied", "reserved"]


def test_retry_returns_receipt_without_regranting_and_binds_parameters():
    ref = dataset()
    assert claim(ref)["granted"]
    replay = claim(ref)
    assert replay["replayed"] and not replay["granted"] and replay["status"] == "reserved"
    reg.finish(ref, "request", "result-hash")
    replay = claim(ref)
    assert replay["status"] == "completed" and replay["result_hash"] == "result-hash"
    assert not replay["granted"]
    assert reg.verify(ref, "request", "study", "frozen-hash", "operator", "result-hash")
    assert not reg.verify(ref, "request", "study", "frozen-hash", "operator", "forged-hash")
    with pytest.raises(ValueError):
        claim(ref, study="changed")
    with pytest.raises(ValueError):
        reg.finish(ref, "request", "replacement")


def test_failed_request_stays_consumed():
    ref = dataset()
    claim(ref)
    reg.finish(ref, "request")
    assert claim(ref)["status"] == "failed"
    assert not claim(ref, "retry")["granted"]


def test_deleted_registry_never_silently_recreated():
    ref = dataset()
    from pathlib import Path
    Path(ref["path"]).unlink()
    with pytest.raises(ValueError):
        reg.status(ref)
    with pytest.raises(ValueError):
        dataset()


def test_replaced_registry_identity_rejected(tmp_path):
    ref = dataset()
    replacement = reg.register("custodian-feed", [("A", "2025-01-01", "2025-01-02")], tmp_path/"other.sqlite")
    with pytest.raises(ValueError):
        reg.status({**ref, "path": replacement["path"]})


def test_missing_receipt_fails_live_verification():
    ref = dataset()
    claim(ref)
    reg.finish(ref, "request", "result")
    with sqlite3.connect(ref["path"]) as db:
        db.execute("DELETE FROM requests")
    assert not reg.verify(ref, "request", "study", "frozen-hash", "operator", "result")


def test_registration_refuses_unrelated_database_without_modifying_it(tmp_path):
    path = tmp_path / "business.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE business (value TEXT)")
        db.execute("INSERT INTO business VALUES ('retain')")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="不是测试登记库"):
        reg.register("custodian-feed", [("A", "2025-01-01", "2025-01-02")], path)
    assert path.read_bytes() == before
    assert not path.with_suffix(".sqlite.identity").exists()


def test_existing_registry_disappearing_at_open_is_not_recreated(monkeypatch):
    from pathlib import Path
    ref = dataset()
    path = Path(ref["path"])
    connect = reg.sqlite3.connect
    def disappear(*args, **kwargs):
        path.unlink()
        return connect(*args, **kwargs)
    monkeypatch.setattr(reg.sqlite3, "connect", disappear)
    with pytest.raises(sqlite3.OperationalError):
        reg.status(ref)
    assert not path.exists()
