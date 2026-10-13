"""Research leakage, lifecycle, accounting and real gate integration tests."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("factor_qc")
pytest.importorskip("lookahead_free")
pytest.importorskip("falsification_ledger")
pytest.importorskip("lesson_book")

from holdout_governance import research as r
from holdout_governance.cli import main
from holdout_governance.engine import run_check


@pytest.fixture
def searched(tmp_path):
    root = tmp_path / "study"
    r.create(root, budget=12)
    r.search(root)
    return root


def test_full_lifecycle_real_tools_and_gate(searched, monkeypatch):
    s = r.inspect(searched)
    assert s["phase"] == "searched" and len(s["trials"]) <= 12
    assert s["trials"][0]["status"] == "rejected"
    assert not s["trials"][0]["timing"]["passed"]
    assert {t["stage"] for t in s["trials"]} == {"discovery", "filtering", "model"}
    assert s["feedback_quality"]["report"]["n_trials"] == len(s["trials"])
    assert not r.audit(searched)["passed"]
    r.freeze(searched)
    s = r.evaluate(searched, "test-operator")
    assert s["phase"] == "evaluated" and s["evaluation_count"] == 1
    assert s["final"]["reviewer"] == "test-operator"
    assert r.audit(searched)["passed"]
    artifact = searched/"evidence"/"artifact.json"
    monkeypatch.chdir(searched.parent)
    result = run_check(str(artifact.relative_to(searched.parent)))
    assert not result["error"]
    assert result["decision"] == "block"  # Never auto-approve the human review.
    assert "review:approved" in result["missing"]
    assert all(g["status"] != "not_run" for g in result["gates"])
    assert (searched/"report.html").exists()


def test_search_never_requests_test_partition(tmp_path, monkeypatch):
    root = tmp_path/"study"
    r.create(root, budget=12)
    original = r._partition
    seen = []
    def guard(root, state, name):
        seen.append(name)
        assert name != "test"
        return original(root, state, name)
    monkeypatch.setattr(r, "_partition", guard)
    r.search(root)
    r.freeze(root)
    assert seen == ["training", "validation", "feedback"]


def test_test_values_cannot_change_search_selection(tmp_path, monkeypatch):
    original = r._synthetic
    def altered():
        x, y, dates = original()
        y[1150:] = -.1
        return x, y, dates
    a, b = tmp_path/"a", tmp_path/"b"
    r.create(a, budget=12)
    s1 = r.search(a)
    monkeypatch.setattr(r, "_synthetic", altered)
    r.create(b, budget=12)
    s2 = r.search(b)
    assert s1["selected"] == s2["selected"]
    assert [t["candidate"] for t in s1["trials"]] == [t["candidate"] for t in s2["trials"]]
    assert [t.get("feedback") for t in s1["trials"]] == [t.get("feedback") for t in s2["trials"]]
    r.freeze(b)
    final = r.evaluate(b)["final"]
    assert not final["outcomes"]["positive_net"]
    assert not r.audit(b, "research_criteria")["passed"]


def test_labels_do_not_cross_windows(tmp_path):
    root = tmp_path/"study"
    state = r.create(root, budget=12)
    for name, window in state["plan"]["windows"].items():
        data = r._partition(root, state, name)
        assert np.all(data["label_dates"] < window["end_exclusive"])
        assert np.all(data["dates"] < data["label_dates"])
        assert window["purged"] == 1


def test_concurrent_evaluation_and_restart_does_not_reset_slot(searched):
    r.freeze(searched)
    def attempt():
        try:
            return r.evaluate(searched)["phase"]
        except ValueError:
            return "denied"
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(outcomes) == ["denied", "evaluated"]
    assert main(["research", "evaluate", "--dir", str(searched), "--reviewer", "again"]) == 2
    assert r.inspect(searched)["evaluation_count"] == 1


def test_failed_test_access_is_consumed(searched):
    r.freeze(searched)
    path = searched/"custody"/"test.npz"
    path.write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="数据版本"):
        r.evaluate(searched)
    state = r.inspect(searched)
    assert state["phase"] == "evaluation_failed" and state["evaluation_count"] == 1
    with pytest.raises(ValueError):
        r.evaluate(searched)


@pytest.mark.parametrize("kind", ["plan", "trial", "budget_reset"])
def test_tampering_is_blocked(searched, kind):
    if kind == "plan":
        plan = json.loads((searched/"plan.json").read_text(encoding="utf-8"))
        plan["budget"] = 100
        r.write_json(searched/"plan.json", plan)
    else:
        with r.connection(searched) as db:
            state = r._load(db)
            if kind == "trial":
                state["trials"][1]["outcome"] = "fake pass"
            else:
                state["trials"] = []
            r._save(db, state)
    with pytest.raises(ValueError):
        r.freeze(searched)


def test_failed_trial_still_counts(tmp_path, monkeypatch):
    root = tmp_path/"study"
    r.create(root, budget=12)
    monkeypatch.setattr(r, "_fit", lambda *args: (_ for _ in ()).throw(ValueError("bad model")))
    state = r.search(root)
    assert len(state["trials"]) > 1
    assert all(t["status"] == "failed" for t in state["trials"][1:])
    assert state["selected"] is None
    with pytest.raises(ValueError):
        r.freeze(root)


def test_interrupted_search_keeps_reserved_trial(tmp_path, monkeypatch):
    root = tmp_path/"study"
    r.create(root, budget=12)
    monkeypatch.setattr(r, "_fit", lambda *args: (_ for _ in ()).throw(RuntimeError("worker died")))
    with pytest.raises(RuntimeError):
        r.search(root)
    state = r.inspect(root)
    assert state["phase"] == "interrupted"
    assert state["trials"][-1]["status"] == "running"
    with pytest.raises(ValueError):
        r.search(root)


@pytest.mark.parametrize("question,budget", [("", 12), ("a", 11), ("a", True), ("a", 101)])
def test_invalid_inputs_do_not_create_study(tmp_path, question, budget):
    with pytest.raises(ValueError):
        r.create(tmp_path/"study", question=question, budget=budget)
    assert not (tmp_path/"study").exists()


def test_missing_dependencies_do_not_leave_partial_study(tmp_path, monkeypatch):
    def missing():
        raise ImportError("missing research tool")
    monkeypatch.setattr(r, "runtime_versions", missing)
    with pytest.raises(ImportError):
        r.create(tmp_path / "study", budget=12)
    assert not (tmp_path / "study").exists()


def test_new_study_and_frozen_copy_cannot_reuse_final_samples(searched, tmp_path, monkeypatch):
    import shutil
    r.freeze(searched)
    copied = tmp_path/"renamed-copy"
    shutil.copytree(searched, copied)
    r.evaluate(searched)
    other = tmp_path/"different-output-parent"/"other-question"
    r.create(other, question="A different research question", budget=12)
    r.search(other)
    r.freeze(other)
    original = r._partition
    def deny_read(root, state, name):
        assert name != "test", "a denied request must not open test bytes"
        return original(root, state, name)
    monkeypatch.setattr(r, "_partition", deny_read)
    for root in (copied, other):
        with pytest.raises(ValueError, match="共用登记处"):
            r.evaluate(root)
        assert r.inspect(root)["evaluation_count"] == 0
        assert not r.audit(root)["passed"]


def test_shared_reservation_survives_local_transaction_crash(searched, monkeypatch):
    r.freeze(searched)
    original = r._save
    def fail_on_consumption(db, state):
        if state["phase"] == "evaluating":
            raise RuntimeError("disk failure after shared reservation")
        original(db, state)
    monkeypatch.setattr(r, "_save", fail_on_consumption)
    with pytest.raises(RuntimeError):
        r.evaluate(searched)
    assert r.inspect(searched)["evaluation_count"] == 0
    monkeypatch.setattr(r, "_save", original)
    with pytest.raises(ValueError, match="共用登记处"):
        r.evaluate(searched)


def test_live_audit_rejects_missing_authority(searched):
    r.freeze(searched)
    state = r.evaluate(searched)
    assert r.audit(searched)["passed"]
    Path(state["plan"]["test_registry"]["path"]).unlink()
    assert not r.audit(searched)["passed"]
    assert r.audit(searched)["registry_error"]


def test_prior_exposure_import_blocks_a_new_study(searched, tmp_path):
    # Import is a conservative declaration, including data seen outside evaluate.
    receipt = r.record_exposure(searched, "historical-custodian")
    assert receipt["recorded_or_already_exposed"]
    other = tmp_path/"new-study"
    r.create(other, budget=12)
    r.search(other)
    r.freeze(other)
    with pytest.raises(ValueError, match="共用登记处"):
        r.evaluate(other)
    assert not r.audit(other)["registry"]["available"]


def test_study_disappearing_at_open_is_not_recreated(tmp_path, monkeypatch):
    import sqlite3
    root = tmp_path / "study"
    r.create(root, budget=12)
    path = root / "research.sqlite"
    connect = r.sqlite3.connect
    def disappear(*args, **kwargs):
        path.unlink()
        return connect(*args, **kwargs)
    monkeypatch.setattr(r.sqlite3, "connect", disappear)
    with pytest.raises(sqlite3.OperationalError):
        r.inspect(root)
    assert not path.exists()


def test_reopening_relocated_study_preserves_state_and_rebinds_live_audits(searched, tmp_path, monkeypatch):
    import shutil
    r.freeze(searched)
    original = r.inspect(searched)
    relocated = tmp_path / "moved" / "study"
    shutil.copytree(searched, relocated)
    monkeypatch.chdir(tmp_path)
    r.render(relocated)
    assert r.inspect(relocated) == original
    inputs = json.loads((relocated / "evidence" / "gate-inputs.json").read_text(encoding="utf-8"))
    for runner in inputs.values():
        assert runner["cwd"] == str((relocated / "evidence").resolve())
        assert runner["cmd"][runner["cmd"].index("--dir") + 1] == str(relocated.resolve())
