"""Reproducible synthetic factor research; trusted local demo, not a sandbox.

Search consumes three public partitions. Only evaluate() opens the held-out
partition. Generated candidates are data (feature subsets/ridge parameters),
never executable code. A custodian must isolate files at the OS/account level
before exposing this workflow to an untrusted agent.
"""
from __future__ import annotations

import hashlib
import html
import importlib.metadata
import json
import math
import sqlite3
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import test_registry

VERSION = "synthetic-factor-research-v1"
FEATURES = ["momentum5", "momentum20", "volume", "stall5", "stall20", "reversal5"]
FEATURE_LABELS = {"momentum5": "5期动量", "momentum20": "20期动量", "volume": "成交量扰动",
                  "stall5": "5期放量滞涨", "stall20": "20期放量滞涨", "reversal5": "5期反转",
                  "future_return": "未来收益（故障对照）"}
FORMULAS = {"momentum5": "过去5期收益均值 / 0.012", "momentum20": "过去20期收益均值 / 0.012",
            "volume": "当期合成成交量标准化扰动", "stall5": "volume × exp(-abs(momentum5))",
            "stall20": "volume × exp(-abs(momentum20))", "reversal5": "-momentum5"}
QUESTIONS = {
    "volume_stall": "放量滞涨是否包含下一交易日的预测信息？",
    "momentum": "短期动量能否改善下一交易日的预测？",
    "reversal": "短期反转是否能通过独立窗口检验？",
}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def digest(value):
    return "sha256:" + hashlib.sha256(encode(value).encode()).hexdigest()


def file_hash(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def runtime_versions():
    return {"python": sys.version, **{name: importlib.metadata.version(name) for name in
            ["numpy", "factor-qc", "lookahead-free", "falsification-ledger", "lesson-book"]}}


def _quality(returns, n_trials, **kwargs):
    from factor_qc.gate import run_gate
    result = run_gate(returns, n_trials, **kwargs)
    missing = []
    def finite(value, path=""):
        if isinstance(value, dict):
            return {k: finite(v, f"{path}.{k}") for k, v in value.items()}
        if isinstance(value, list):
            return [finite(v, f"{path}[{i}]") for i,v in enumerate(value)]
        if isinstance(value, float) and not math.isfinite(value):
            missing.append(path)
            return None
        return value
    result = finite(result)
    if missing:
        result["passed"] = False
        result["non_finite_fields"] = missing
        result["verdict"] = "FAIL - undefined/infinite statistics; stored as null, never as a pass"
    return result


def write_json(path, value):
    Path(path).write_text(encode(value), encoding="utf-8")


@contextmanager
def connection(root):
    path = (Path(root) / "research.sqlite").resolve()
    if not path.is_file():
        raise ValueError("研究记录不存在，请先创建研究。")
    # Readers of an existing study must never silently recreate a missing DB.
    db = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=30)
    try:
        db.execute("BEGIN IMMEDIATE")
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def _load(db):
    return json.loads(db.execute("SELECT body FROM state WHERE id=1").fetchone()[0])


def _save(db, state):
    db.execute("UPDATE state SET body=? WHERE id=1", (encode(state),))


def _event(state, kind, **details):
    previous = state["events"][-1]["hash"] if state["events"] else None
    item = {"at": now(), "kind": kind, "details": details, "previous": previous}
    item["hash"] = digest(item)
    state["events"].append(item)


def _verify(root, state):
    if digest(state["plan"]) != state["plan_hash"]:
        raise ValueError("冻结方案已改变，研究被拦截。")
    if file_hash(Path(root) / "plan.json") != state["plan_file_hash"]:
        raise ValueError("方案文件已改变，不能继续研究。")
    if file_hash(__file__) != state["engine_hash"]:
        raise ValueError("研究程序版本已改变，请保留旧版本或新建研究。")
    if file_hash(test_registry.__file__) != state["plan"].get("registry_engine_hash"):
        raise ValueError("测试登记程序版本已改变，请恢复冻结版本。")
    if runtime_versions() != state["plan"]["runtime"]:
        raise ValueError("研究运行环境已改变，请恢复冻结版本。")
    previous = None
    for event in state["events"]:
        payload = {k: v for k, v in event.items() if k != "hash"}
        if event["previous"] != previous or digest(payload) != event["hash"]:
            raise ValueError("研究事件记录不完整。")
        previous = event["hash"]
    starts = [e for e in state["events"] if e["kind"] == "trial_started"]
    finishes = {e["details"]["id"]: e for e in state["events"] if e["kind"] == "trial_finished"}
    if len(starts) != len(state["trials"]) or len(starts) > state["plan"]["budget"]:
        raise ValueError("试验次数与事件账本不一致。")
    for index, trial in enumerate(state["trials"], 1):
        if trial["id"] != index or digest(trial["candidate"]) != starts[index-1]["details"]["candidate_hash"]:
            raise ValueError("候选内容与登记记录不一致。")
        if index in finishes and digest(trial) != finishes[index]["details"]["result_hash"]:
            raise ValueError("试验结果与事件记录不一致。")
        if trial["status"] != "running" and index not in finishes:
            raise ValueError("试验缺少完成记录。")
    accesses = [e for e in state["events"] if e["kind"] == "test_access_started"]
    if len(accesses) != state["evaluation_count"] or len(accesses) > 1:
        raise ValueError("测试访问次数与事件记录不一致。")
    completed = [e for e in state["events"] if e["kind"] == "test_access_finished"]
    if state["final"] is not None and (len(completed) != 1 or digest(state["final"]) != completed[0]["details"]["report_hash"]):
        raise ValueError("最终结果已改变或缺少评估凭证。")
    if state.get("frozen") and (digest(state["frozen"]) != state["frozen_hash"] or
                               state["selected"] != state["frozen"]["trial_id"] or
                               digest(state["trials"]) != state["frozen"]["trials_hash"]):
        raise ValueError("冻结候选或试验记录已改变。")


def inspect(root):
    with connection(root) as db:
        state = _load(db)
        _verify(root, state)
        return state


def record_exposure(root, reviewer):
    """Conservatively import a known exposure from an older synthetic run.

    This imports a contamination notice, not a scientific validity certificate;
    the old engine need not be executable. No return values are read or scored.
    """
    with connection(root) as db:
        state = _load(db)
    plan = state["plan"]
    if digest(plan) != state["plan_hash"] or file_hash(Path(root)/"plan.json") != state["plan_file_hash"]:
        raise ValueError("历史研究方案校验失败。")
    if plan.get("synthetic") is not True or plan.get("seed") != 20260909:
        raise ValueError("此入口只导入本工作台的合成样本历史；真实数据需由保管方登记。")
    spec = plan["data"]["test"]
    path = (Path(root)/spec["path"]).resolve()
    if not path.is_relative_to(Path(root).resolve()) or file_hash(path) != spec["hash"]:
        raise ValueError("历史测试文件版本不一致。")
    with np.load(path, allow_pickle=False) as data:
        dates, labels = data["dates"], data["label_dates"]
    if len(dates) != len(labels):
        raise ValueError("历史样本日期记录不完整。")
    ref = test_registry.register("holdout-synthetic-seed-20260909",
             [(f"asset-{a:02d}", str(d), str(label)) for d, label in zip(dates, labels) for a in range(24)])
    request_id = "prior-exposure:" + digest([state["plan_hash"], str(Path(root).resolve())])
    receipt = test_registry.claim(ref, request_id, "prior-exposure", state["plan_hash"], reviewer)
    if receipt["granted"]:
        test_registry.finish(ref, request_id, digest({"notice": "prior exposure; not an evaluation certificate",
                                                    "source_plan_hash": state["plan_hash"]}))
    return {"recorded_or_already_exposed": True, "test_registry": ref, "request_id": request_id,
            "scope": "prior-exposure notice only; no approval of historical results"}


def _synthetic():
    # Fixed seed deliberately not an input: repeated runs are not new evidence.
    rng = np.random.default_rng(20260909)
    n, assets = 1471, 24
    returns = np.zeros((n, assets))
    volume = rng.normal(size=(n, assets))
    features = np.zeros((n, assets, len(FEATURES)))
    for t in range(21, n - 1):
        m5 = returns[t-5:t].mean(axis=0) / .012
        m20 = returns[t-20:t].mean(axis=0) / .012
        v = volume[t]
        features[t] = np.array([m5, m20, v, v * np.exp(-abs(m5)),
                                v * np.exp(-abs(m20)), -m5]).T
        # Educational planted effect, deliberately stated in UI and report.
        returns[t+1] = .003 * features[t, :, 3] - .0005*m5 + rng.normal(0, .012, assets)
    x = features[21:-1]
    y = returns[22:]
    dates = np.busday_offset("2018-01-01", np.arange(len(y))).astype(str)
    return x, y, dates


def create(root, question=QUESTIONS["volume_stall"], budget=30, family="volume_stall"):
    if not isinstance(question, str) or not question.strip() or len(question) > 500:
        raise ValueError("请输入1到500字的研究问题。")
    if type(budget) is not int or not 12 <= budget <= 100:
        raise ValueError("试验预算需为12到100之间的整数。")
    if family not in QUESTIONS:
        raise ValueError("请选择支持的研究方向。")
    runtime = runtime_versions()
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    (root / "custody").mkdir()
    (root / "data").mkdir()
    x, y, dates = _synthetic()
    edges = [0, 650, 900, 1150, len(y)]
    windows, files = {}, {}
    for name, lo, hi in zip(["training", "validation", "feedback", "test"], edges, edges[1:]):
        # Drop the last signal: its one-day label would touch the next window.
        path = root / ("custody" if name == "test" else "data") / f"{name}.npz"
        np.savez(path, x=x[lo:hi-1], y=y[lo:hi-1], dates=dates[lo:hi-1],
                 label_dates=dates[lo+1:hi])
        windows[name] = {"start": str(dates[lo]), "end_exclusive":
                         str(dates[hi]) if hi < len(dates) else str(np.busday_offset(dates[-1], 1)),
                         "samples": hi-lo-1, "purged": 1}
        files[name] = {"path": str(path.relative_to(root)), "hash": file_hash(path)}
    custody = test_registry.register("holdout-synthetic-seed-20260909",
                [(f"asset-{asset:02d}", str(dates[i]), str(dates[i+1]))
                 for i in range(1150, len(y)-1) for asset in range(y.shape[1])])
    plan = {"version": VERSION, "question": question.strip(), "family": family,
            "study_id": str(uuid.uuid4()), "case_id": root.name,
            "test_registry": custody, "registry_engine_hash": file_hash(test_registry.__file__),
            "budget": budget, "windows": windows, "data": files,
            "runtime": runtime,
            "cost_bps": 10, "stress_cost_multiplier": 2,
            "criteria": [{"name": n, "required": True} for n in
                         ["positive_net", "stress_positive", "statistical_quality"]],
            "selection": "validation positive-net eligibility, then feedback annual Sharpe; each ridge choice counts as one trial",
            "synthetic": True, "seed": 20260909,
            "planted_signal": "next return = 0.003*stall5 - 0.0005*momentum5 + N(0,0.012); educational, not market calibrated",
            "execution": "synthetic next-session equal-weight top-5; not an exchange simulator"}
    write_json(root / "plan.json", plan)
    state = {"plan": plan, "plan_hash": digest(plan), "plan_file_hash": file_hash(root / "plan.json"),
             "engine_hash": file_hash(__file__), "phase": "ready", "trials": [],
             "events": [], "selected": None, "final": None, "evaluation_count": 0}
    _event(state, "preregistered")
    from falsification_ledger.ledger import register_prediction
    register_prediction(root / "preregister", root.name, "support", question.strip(),
                        falsification_contract={"criteria": plan["criteria"], "plan_hash": state["plan_hash"]})
    db = sqlite3.connect(root / "research.sqlite")
    try:
        db.execute("CREATE TABLE state (id INTEGER PRIMARY KEY, body TEXT NOT NULL)")
        db.execute("INSERT INTO state VALUES (1, ?)", (encode(state),))
        db.commit()
    finally:
        db.close()
    render(root)
    return state


def _partition(root, state, name):
    spec = state["plan"]["data"][name]
    path = Path(root) / spec["path"]
    if file_hash(path) != spec["hash"]:
        raise ValueError("数据版本发生变化，评估已停止。")
    with np.load(path, allow_pickle=False) as data:
        result = {k: data[k].copy() for k in data.files}
    w = state["plan"]["windows"][name]
    if not (np.all(result["dates"] >= w["start"]) and
            np.all(result["label_dates"] < w["end_exclusive"]) and
            np.all(result["dates"] < result["label_dates"])):
        raise ValueError("样本或收益标签跨越冻结窗口。")
    return result


def _timing(candidate):
    from lookahead_free.checks import check_pipeline
    from lookahead_free.model import Pipeline, Operation
    future = "future_return" in candidate["features"]
    return check_pipeline(Pipeline("synthetic-factor", [
        Operation("features", "read", release="2020-01-03T16:00:00" if future else "2020-01-02T16:00:00"),
        Operation("decision", "decision", inputs=["features"], decision_time="2020-01-03T09:30:00")]))


def _fit(data, names, ridge):
    columns = [FEATURES.index(n) for n in names]
    x = data["x"][:, :, columns].reshape(-1, len(columns))
    y = data["y"].ravel()
    mean, std = x.mean(axis=0), x.std(axis=0)
    std = np.maximum(std, 1e-8)
    z = (x - mean) / std
    center = float(y.mean())
    coef = np.linalg.solve(z.T @ z + ridge * np.eye(len(columns)), z.T @ (y-center))
    return {"features": names, "ridge": ridge, "mean": mean.tolist(), "std": std.tolist(),
            "coef": coef.tolist(), "intercept": center}


def _score(data, model, cost_bps):
    cols = [FEATURES.index(n) for n in model["features"]]
    scores = ((data["x"][:, :, cols]-model["mean"])/model["std"]) @ model["coef"] + model["intercept"]
    weights = np.zeros(scores.shape)
    winners = np.argsort(scores, axis=1, kind="stable")[:, -5:]
    np.put_along_axis(weights, winners, .2, axis=1)
    prior = np.vstack([np.zeros((1, weights.shape[1])), weights[:-1]])
    turnover = np.abs(weights - prior).sum(axis=1)
    gross = (weights*data["y"]).sum(axis=1)
    # Include final liquidation, so every partition pays both entry and exit.
    turnover[-1] += weights[-1].sum()
    net = gross - turnover * cost_bps / 10000
    stress = gross - turnover * cost_bps * 2 / 10000
    sd = float(net.std(ddof=1))
    sharpe = float(net.mean()/sd*math.sqrt(252)) if sd > 1e-12 else 0.0
    equity = np.cumprod(1+net)
    peak = np.maximum.accumulate(np.r_[1.0, equity])[1:]
    return {"sharpe": sharpe, "annual_mean": float(net.mean()*252),
            "max_drawdown": float(np.min(equity/peak-1)),
            "stress_annual_mean": float(stress.mean()*252),
            "returns": net.tolist(), "dates": data["dates"].tolist(), "equity": equity.tolist()}


def _trial(root, candidate, stage, operation, reason, public):
    """Reserve before calculation. Failed and interrupted trials consume budget."""
    with connection(root) as db:
        state = _load(db)
        _verify(root, state)
        if state["phase"] != "searching" or len(state["trials"]) >= state["plan"]["budget"]:
            raise ValueError("研究已停止或预算已用完。")
        number = len(state["trials"]) + 1
        trial = {"id": number, "stage": stage, "operation": operation, "reason": reason,
                 "candidate": candidate, "candidate_hash": digest(candidate),
                 "status": "running", "started_at": now()}
        state["trials"].append(trial)
        _event(state, "trial_started", id=number, candidate_hash=trial["candidate_hash"])
        _save(db, state)
    try:
        timing = _timing(candidate)
        trial["timing"] = timing
        if not timing["passed"]:
            trial.update(status="rejected", outcome="时序检查拒绝：候选引用了未来收益。")
        elif any(t.get("candidate_hash") == trial["candidate_hash"] for t in state["trials"][:-1]):
            trial.update(status="rejected", outcome="重复候选，已记录本次尝试，不重复计算。")
        else:
            model = _fit(public["training"], candidate["features"], candidate["ridge"])
            validation = _score(public["validation"], model, state["plan"]["cost_bps"])
            feedback = _score(public["feedback"], model, state["plan"]["cost_bps"])
            # Validation is a frozen eligibility rule, never the test partition.
            eligible = validation["annual_mean"] > 0
            trial.update(status="accepted" if eligible else "rejected", model=model,
                         validation=validation, feedback=feedback,
                         outcome="验证期扣费后均值为正，保留候选供比较。" if eligible else
                         "验证期扣费后均值不为正，淘汰。")
    except (ValueError, FloatingPointError, np.linalg.LinAlgError) as exc:
        trial.update(status="failed", outcome=f"计算失败：{exc}")
    trial["finished_at"] = now()
    with connection(root) as db:
        state = _load(db)
        state["trials"][number-1] = trial
        _event(state, "trial_finished", id=number, result_hash=digest(trial))
        _save(db, state)
    return trial


def _rank(trials):
    return sorted([t for t in trials if t["status"] == "accepted"],
                  key=lambda t: (-t["feedback"]["sharpe"], t["id"]))


def search(root, progress=None):
    from lesson_book.lessons import append_record, match_lessons, new_record
    with connection(root) as db:
        state = _load(db)
        _verify(root, state)
        if state["phase"] != "ready":
            raise ValueError("本轮搜索已运行；请查看现有结果，不能清零预算重跑。")
        state["phase"] = "searching"
        _event(state, "search_started")
        _save(db, state)
    try:
        # No test path is opened by this search function or its candidate helpers.
        public = {k: _partition(root, state, k) for k in ["training", "validation", "feedback"]}
        budget = state["plan"]["budget"]
        book = Path(root).parent / "research-lessons.jsonl"
        lessons = match_lessons("", "synthetic", .012, tags=("research",), path=book)
        trials = []
        best, stale = -1e20, 0
        ordering = {"volume_stall": [3, 4, 2, 0, 1, 5], "momentum": [0, 1, 3, 2, 4, 5],
                    "reversal": [5, 0, 4, 1, 3, 2]}[state["plan"]["family"]]
        rng = np.random.default_rng(904)

        def run(candidate, stage, operation, reason):
            nonlocal best, stale
            t = _trial(root, candidate, stage, operation, reason, public)
            trials.append(t)
            score = t.get("feedback", {}).get("sharpe", -1e20) if t["status"] == "accepted" else -1e20
            if score > best + .01:
                best, stale = score, 0
            else:
                stale += 1
            if progress:
                progress(t)
            return t

        # One explicitly labelled negative control proves the temporal gate runs.
        run({"features": ["future_return"], "ridge": 10.0}, "discovery", "Pivot",
            "故障对照：故意提出未来数据候选，验证门禁。")
        for i in range(max(6, int(budget*.55))-1):
            ranked = _rank(trials)
            if i < len(ordering):
                names, operation = [FEATURES[ordering[i]]], "Pivot"
                reason = "按选定研究方向探索一个不同的基础因子。"
            elif stale >= 3 and len(ranked) >= 2:
                names = sorted(set(ranked[0]["candidate"]["features"] + ranked[1]["candidate"]["features"]))
                operation, reason = "Combine", "连续改进不足，组合两个反馈表现较好的方向。"
                if len(names) == 1:
                    names.append(FEATURES[ordering[i % 6]])
                    names = sorted(set(names))
            else:
                names = sorted(rng.choice(FEATURES, size=2 if i % 2 else 3, replace=False).tolist())
                operation, reason = "Improve", "改变因子输入组合，保留可解释的线性预测。"
            run({"features": names, "ridge": 10.0}, "discovery", operation, reason)
            if i >= 8 and stale >= 6:
                break

        ranked = _rank(trials)
        if ranked:
            # Subset search: remove/add features; compare portfolio feedback,
            # rather than claiming a factor's standalone score guarantees value.
            union = list(dict.fromkeys(n for t in ranked[:4] for n in t["candidate"]["features"]))
            filter_count = min(max(2, budget//4), budget-len(trials)-3)
            for i in range(filter_count):
                if i == 0:
                    names = union
                elif len(union) > 1:
                    names = [n for j, n in enumerate(union) if j != (i-1) % len(union)]
                else:
                    names = sorted(set(union + [FEATURES[ordering[i % 6]]]))
                run({"features": sorted(names), "ridge": 10.0}, "filtering",
                    "Combine" if i == 0 else "Improve", "增删因子，重新训练并比较组合的反馈表现。")
            shortlisted = _rank(trials)
            base = shortlisted[0]["candidate"]["features"]
            # Each ridge choice is a separate counted experiment. No hidden grid.
            for ridge in [.01, .1, 1., 100., 1000., 10000.]:
                if len(trials) >= budget:
                    break
                run({"features": base, "ridge": ridge}, "model", "Improve",
                    "调整线性模型的正则强度；每个参数配置单独计数。")
        ranked = _rank(trials)
        selected = ranked[0]["id"] if ranked else None
        measured = [t for t in trials if "feedback" in t]
        quality = None
        if selected:
            quality = _quality(np.array(trials[selected-1]["feedback"]["returns"]), len(trials),
                               trials_matrix=np.array([t["feedback"]["returns"] for t in measured]).T,
                               n_blocks=8)
        append_record(book, new_record(title="未来数据候选被门禁拦截", date=now()[:10],
                      industry="synthetic", tags=("research", "lookahead"),
                      category="temporal_leakage", priority="P0",
                      lesson="收益标签只能用于评分，不能作为候选因子的当时输入。"))
        with connection(root) as db:
            state = _load(db)
            state.update(phase="searched", selected=selected, feedback_quality=quality,
                         prior_lessons=lessons)
            _event(state, "Stop", reason="候选空间已完成或边际改进不足；未用预算保留，不填充无意义试验。",
                   used=len(trials), budget=budget)
            _save(db, state)
    except BaseException:
        with connection(root) as db:
            state = _load(db)
            state["phase"] = "interrupted"
            _event(state, "search_interrupted", reason="已开始的尝试保留，禁止当作完整搜索放行。")
            _save(db, state)
        raise
    render(root)
    return inspect(root)


def freeze(root):
    from falsification_ledger.ledger import verify_chain
    with connection(root) as db:
        state = _load(db)
        _verify(root, state)
        if state["phase"] != "searched" or not state["selected"]:
            raise ValueError("需要完成搜索且存在可评估候选，才能冻结。")
        if not verify_chain(Path(root)/"preregister")["ok"]:
            raise ValueError("预注册记录校验失败。")
        if any(t["status"] == "running" for t in state["trials"]):
            raise ValueError("存在未完成试验，禁止冻结。")
        chosen = _rank(state["trials"])[0]
        if chosen["id"] != state["selected"]:
            raise ValueError("选中候选与冻结的反馈排序规则不一致。")
        state["frozen"] = {"plan_hash": state["plan_hash"], "trial_id": chosen["id"],
                           "model": chosen["model"], "trials_hash": digest(state["trials"]),
                           "n_trials": len(state["trials"]), "at": now()}
        state["frozen_hash"] = digest(state["frozen"])
        state["phase"] = "frozen"
        _event(state, "candidate_frozen", frozen_hash=state["frozen_hash"])
        _save(db, state)
    render(root)
    return inspect(root)


def evaluate(root, reviewer="local-operator"):
    if not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer) > 100:
        raise ValueError("请填写执行评估的人，最多100字。")
    with connection(root) as db:
        state = _load(db)
        _verify(root, state)
        if state["phase"] != "frozen" or state["evaluation_count"]:
            raise ValueError("本轮必须先冻结，且最终测试仅允许执行一次；重启也不会重置。")
        if digest(state["frozen"]) != state["frozen_hash"] or digest(state["trials"]) != state["frozen"]["trials_hash"]:
            raise ValueError("冻结后的候选或试验记录已改变。")
        request_id = digest([state["plan"]["study_id"], state["frozen_hash"]])
        receipt = test_registry.claim(state["plan"]["test_registry"], request_id,
                    state["plan"]["study_id"], state["frozen_hash"], reviewer.strip())
        if not receipt["granted"]:
            # Replaying a copied or interrupted request never executes again.
            raise ValueError(f"共用登记处拒绝开启测试：{receipt['status']}；同一或重叠样本已有使用记录。申请 {request_id}")
        # Commit access consumption BEFORE opening test bytes. Errors do not
        # restore the slot: a crashed evaluator may already have observed data.
        state.update(phase="evaluating", evaluation_count=1, test_request_id=request_id)
        _event(state, "test_access_started", reviewer=reviewer.strip(), frozen_hash=state["frozen_hash"])
        _save(db, state)
    try:
        data = _partition(root, state, "test")
        final = _score(data, state["frozen"]["model"], state["plan"]["cost_bps"])
        from falsification_ledger.contracts import criteria_conformance
        from falsification_ledger.ledger import conclude_prediction, prediction_contract, verify_chain
        # PBO is computed on the feedback trial matrix only. Evaluating all
        # candidates on test would expose a fresh selection opportunity.
        final_quality = _quality(np.array(final["returns"]), len(state["trials"]))
        outcomes = {"positive_net": final["annual_mean"] > 0,
                    "stress_positive": final["stress_annual_mean"] > 0,
                    "statistical_quality": bool(final_quality["passed"] and state["feedback_quality"]["passed"])}
        report = {"conclusion": "not_falsified" if all(outcomes.values()) else "falsified",
                  "criteria_outcomes": [{"name": k, "outcome": "met" if v else "violated"} for k,v in outcomes.items()]}
        contract = prediction_contract(Path(root)/"preregister", state["plan"]["case_id"])
        if not contract or contract.get("plan_hash") != state["plan_hash"]:
            raise ValueError("预注册方案与冻结方案不一致。")
        issues = criteria_conformance(contract, report)
        conclude_prediction(Path(root)/"preregister", state["plan"]["case_id"],
                            "support" if all(outcomes.values()) and not issues else "against")
        final.update(quality=final_quality, outcomes=outcomes, conformance=issues,
                     ledger_ok=verify_chain(Path(root)/"preregister")["ok"], reviewer=reviewer.strip(),
                     evaluated_at=now(), pbo_scope="feedback trial matrix only; no test candidate sweep")
        test_registry.finish(state["plan"]["test_registry"], request_id, digest(final))
        with connection(root) as db:
            state = _load(db)
            state.update(phase="evaluated", final=final)
            _event(state, "test_access_finished", report_hash=digest(final))
            _save(db, state)
    except BaseException:
        # If receipt completion already committed, leave it intact; a local
        # write failure cannot authorize another exposure.
        try:
            test_registry.finish(state["plan"]["test_registry"], request_id)
        except (ValueError, sqlite3.Error, OSError):
            pass
        with connection(root) as db:
            state = _load(db)
            state["phase"] = "evaluation_failed"
            _event(state, "test_access_failed", reason="测试机会已消耗；不能重试后挑选结果。")
            _save(db, state)
        raise
    render(root)
    return inspect(root)


def audit(root, gate="holdout_usage"):
    """Live evidence for gov runners. No test data or evaluation is opened here."""
    from falsification_ledger.ledger import prediction_contract, verify_chain
    state = inspect(root)
    final = state["final"]
    registry_ok, registry_error = False, None
    try:
        registry_status = test_registry.status(state["plan"]["test_registry"])
        if final:
            registry_ok = test_registry.verify(state["plan"]["test_registry"], state.get("test_request_id"),
                            state["plan"]["study_id"], state["frozen_hash"], final["reviewer"], digest(final))
    except (ValueError, sqlite3.Error, OSError) as exc:
        registry_status, registry_error = {"available": False}, str(exc)
    checks = {
        "holdout_usage": state["phase"] == "evaluated" and state["evaluation_count"] == 1 and registry_ok,
        "temporal_integrity": bool(state["selected"]) and state["trials"][state["selected"]-1]["timing"]["passed"],
        "statistical_quality": bool(final and final["outcomes"]["statistical_quality"]),
        "preregistration": bool(final and not final["conformance"] and
                                 verify_chain(Path(root)/"preregister")["ok"] and
                                 prediction_contract(Path(root)/"preregister", state["plan"]["case_id"]).get("plan_hash") == state["plan_hash"]),
        "research_criteria": bool(final and all(final["outcomes"].values())),
    }
    if gate not in checks:
        raise ValueError("未知的研究检查。")
    if state.get("frozen"):
        checks["holdout_usage"] &= (digest(state["frozen"]) == state["frozen_hash"] and
                                    digest(state["trials"]) == state["frozen"]["trials_hash"])
    return {"gate": gate, "passed": bool(checks[gate]), "phase": state["phase"],
            "plan_hash": state["plan_hash"], "n_trials": len(state["trials"]),
            "test_access_count": state["evaluation_count"], "synthetic": True,
            "scope": "trusted local workflow; not OS-level isolation",
            "registry": registry_status, "registry_receipt_valid": registry_ok,
            "registry_error": registry_error, "request_id": state.get("test_request_id"),
            "frozen_hash": state.get("frozen_hash"), "final_hash": digest(final) if final else None}


PHASES = {"ready": "已登记 · 等待搜索", "searching": "搜索中", "searched": "搜索完成 · 等待冻结",
          "frozen": "候选已冻结 · 测试尚未开启", "evaluating": "最终评估中", "evaluated": "最终评估完成",
          "interrupted": "搜索中断 · 不可放行", "evaluation_failed": "最终评估失败 · 机会已消耗"}
STAGES = {"discovery": "因子发现", "filtering": "因子筛选", "model": "模型优化"}


def render(root):
    """Export a readable, portable report plus live gov gate configuration."""
    from .engine import run_init, run_check
    from .policy import sha256_file
    root = Path(root).resolve()
    state = inspect(root)
    evidence = root / "evidence"
    if not (evidence / "artifact.json").exists():
        run_init(str(evidence), name=root.name)
        gates = ["temporal_integrity", "statistical_quality", "preregistration", "research_criteria", "holdout_usage"]
        policy = {"schema_version": "holdout.policy.v0.1", "defaults": {"missing_gate": "block", "gate_warn": "review_needed"},
                  "kinds": {"research_conclusion": {"required_gates": gates, "required_attachments": ["limitations"],
                                                     "severity": "block", "requires_review": True}}}
        # JSON is valid YAML; this avoids a second serialization convention.
        write_json(evidence/"policy.yml", policy)
        artifact = json.loads((evidence/"artifact.json").read_text(encoding="utf-8"))
        artifact["policy_ref"] = sha256_file(evidence/"policy.yml")
        artifact["producer"] = {"type": "hybrid", "model_id": "deterministic-search-no-LLM"}
        artifact["attachments"] = {"limitations": "../limitations.txt"}
        write_json(evidence/"artifact.json", artifact)
    # A relocated/copied study must audit its own current files, never the
    # original directory recorded when the report was first created.
    gates = ["temporal_integrity", "statistical_quality", "preregistration", "research_criteria", "holdout_usage"]
    executable = str(Path(sys.executable).with_name("python.exe")) if Path(sys.executable).name.lower() == "pythonw.exe" else sys.executable
    write_json(evidence/"gate-inputs.json", {g: {"cwd": str(evidence), "cmd": [executable, "-m", "holdout_governance",
               "research", "audit", "--dir", str(root), "--gate", g]} for g in gates})
    limitations = ("合成数据，内置可学习信号；固定种子重复实验不是新证据。\n"
                  "跨研究登记按来源、资产和标签时间识别重叠；失败也消耗机会，不提供清零。\n"
                  "登记仅覆盖同一可信登记处记录的访问；历史未登记暴露、私下读取和换库无法据此证明不存在。\n"
                  "候选为预设特征与线性模型配置，不调用大模型，不执行生成代码。\n"
                  "本地工作流隔离，不是操作系统沙箱；能读写研究文件的同一账号可绕过限制。\n"
                  "未使用真实A股、真实复权或交易撮合，不声称接入了数据免疫和复权检查。\n"
                  "验证/反馈/测试独立结算进出成本；反馈指标不是最终结果。\n"
                  "PBO仅使用反馈期试验矩阵，未在最终测试遍历所有候选。\n"
                  "数据标签边界已剔除；输入特征时间检查基于受控生成器的声明。\n"
                  "通过表示满足演示标准，不代表盈利；人工审核未自动批准。\n")
    (root/"limitations.txt").write_text(limitations, encoding="utf-8")
    # Directly use the same real audits here; gov check can rerun them via CLI.
    # run_check with empty inputs keeps export cheap and deterministic.
    from .engine import run_attach
    for gate in ["temporal_integrity", "statistical_quality", "preregistration", "research_criteria", "holdout_usage"]:
        report = audit(root, gate)
        write_json(evidence/f"{gate}.json", report)
        run_attach(str(evidence/"artifact.json"), gate=gate, status="pass" if report["passed"] else "fail",
                   tool="holdout-research", report_ref=file_hash(evidence/f"{gate}.json"), tool_version=VERSION)
    write_json(evidence/"export-only-inputs.json", {})
    governance = run_check(str(evidence/"artifact.json"), gate_inputs=str(evidence/"export-only-inputs.json"))
    write_json(root/"summary.json", {"plan": state["plan"], "phase": state["phase"],
               "selected": state["selected"], "trials": state["trials"], "final": state["final"],
               "events": state["events"], "governance": governance["decision"]})
    esc = lambda v: html.escape(str(v), quote=True)
    rows = []
    for t in state["trials"]:
        m = t.get("feedback", {})
        details = {"proposal": t["candidate"], "formula_definitions": {n: FORMULAS.get(n, "禁止：未来收益标签") for n in t["candidate"]["features"]},
                   "model": t.get("model"), "timing": t.get("timing"),
                   "started_at": t["started_at"], "candidate_hash": t["candidate_hash"]}
        rows.append(f'<tr><td>#{t["id"]}</td><td>{STAGES[t["stage"]]}</td><td>{esc(t["operation"])}</td>'
                    f'<td>{esc(", ".join(FEATURE_LABELS[n] for n in t["candidate"]["features"]))}</td><td>{format(m["sharpe"], ".2f") if m else "—"}</td>'
                    f'<td><details><summary>{esc(t.get("outcome", "计算中"))}</summary><p>{esc(t["reason"])}</p>'
                    f'<pre>{esc(json.dumps(details, ensure_ascii=False, indent=2))}</pre></details></td></tr>')
    final = state["final"]
    custody_audit = audit(root)
    custody_text = ("共用登记处凭证已核验" if custody_audit["registry_receipt_valid"] else
                    "登记处尚无本研究的完成凭证；" + ("样本可申请一次评估" if custody_audit["registry"].get("available") else "样本已占用或登记处不可用，禁止开启"))
    final_text = "最终测试尚未开启；候选排序只使用反馈窗口。"
    if final:
        final_text = (f'最终测试：扣费后日均收益年化 {final["annual_mean"]:.2%}，'
                      f'成本翻倍 {final["stress_annual_mean"]:.2%}，最大回撤 {final["max_drawdown"]:.2%}。'
                      f'预注册标准：{"全部满足" if all(final["outcomes"].values()) else "未全部满足"}。')
    windows = "".join(f'<div><b>{esc(label)}</b><p>{v["start"]} → {v["end_exclusive"]}（不含）</p>'
                      f'<small>{v["samples"]}天 · 剔除边界标签{v["purged"]}天</small></div>'
                      for k,label in [("training", "训练"), ("validation", "验证"), ("feedback", "搜索反馈"), ("test", "最终测试")]
                      for v in [state["plan"]["windows"][k]])
    criteria_html = ""
    if final:
        names = {"positive_net": "扣费后日均收益为正", "stress_positive": "成本翻倍后日均收益为正",
                 "statistical_quality": "反馈与最终窗口的统计质量均通过"}
        criteria_html = "<ul>" + "".join(f'<li>{names[k]}：{"通过" if v else "未通过"}</li>' for k,v in final["outcomes"].items()) + "</ul>"
        criteria_html += '<details><summary>展开统计检查详情（反馈与最终分别记录）</summary><pre>' + esc(json.dumps({
            "反馈": state["feedback_quality"], "最终": final["quality"]}, ensure_ascii=False, indent=2)) + '</pre></details>'
    document = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Holdout 因子研究报告</title><style>
body{{margin:0;background:#f4f5f0;color:#1c302c;font:15px/1.65 system-ui,"Microsoft YaHei",sans-serif}}main{{max-width:1200px;margin:auto;padding:36px 24px}}
header{{border-bottom:2px solid #1c5649;padding-bottom:20px}}h1{{font-size:30px;margin:8px 0}}.tag{{color:#69541d;background:#eee4c6;padding:5px 10px;border-radius:6px}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:24px 0}}.grid>div,section{{background:white;border:1px solid #dbe2d8;border-radius:10px;padding:18px}}
table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:12px 8px;border-bottom:1px solid #e5e9e1;vertical-align:top}}th{{font-size:12px;color:#687972}}pre{{white-space:pre-wrap;word-break:break-word;font-size:12px}}summary{{cursor:pointer}}small{{color:#63746c}}a{{color:#1b705c}}.scroll{{overflow:auto}}@media(max-width:700px){{.grid{{grid-template-columns:1fr 1fr}}h1{{font-size:24px}}}}
</style><main><header><span class="tag">合成数据演示 · 固定规则搜索 · 不含真实策略</span><h1>{esc(state["plan"]["question"])}</h1>
<p>{PHASES[state["phase"]]} · 已用 {len(state["trials"])}/{state["plan"]["budget"]} 次 · 选中候选 {state["selected"] or "无"} · 最终测试访问 {state["evaluation_count"]} 次</p></header>
<div class="grid">{windows}</div><section><h2>最终评估</h2><p>{esc(final_text)}</p>{criteria_html}<p>治理结论：{esc(governance["decision"])}。最终评估操作不会代替人工批准。</p>
<p>最终测试使用治理：{esc(custody_text)}。</p><a href="evidence/holdout_usage.json">查看共用登记处核验</a> · <a href="summary.json">完整研究记录</a> · <a href="plan.json">冻结方案</a> · <a href="evidence/artifact.json">证据清单</a></section>
<h2>候选与淘汰原因 <small>下表数值均为反馈期 Sharpe</small></h2><div class="scroll"><table><thead><tr><th>编号</th><th>阶段</th><th>动作</th><th>因子输入</th><th>反馈</th><th>结果 / 点击查看证据</th></tr></thead><tbody>{''.join(rows) or '<tr><td colspan="6">还没有试验。请在工作台开始搜索。</td></tr>'}</tbody></table></div>
<h2>能力边界</h2><pre>{esc(limitations)}</pre><small>方案指纹：{esc(state["plan_hash"])}<br>由本地受控计算生成，没有调用外部模型或发送数据。</small></main></html>'''
    (root/"report.html").write_text(document, encoding="utf-8")
    return root/"report.html"
