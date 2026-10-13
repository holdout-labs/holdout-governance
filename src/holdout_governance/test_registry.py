"""Shared, fail-closed holdout exposure records for trusted local operators.

Identity is custodian-supplied lineage, asset and inclusive label interval.
File paths, serialization and row order never grant another exposure. This
registry is not an access-control boundary against its filesystem owner.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _hash(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def default_path():
    return Path(os.environ.get("HOLDOUT_TEST_REGISTRY", Path.home()/".holdout"/"test-use.sqlite")).resolve()


@contextmanager
def _db(path, expected=None, initialize=False):
    path = Path(path).resolve()
    anchor = path.with_suffix(path.suffix + ".identity")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not initialize and (not path.is_file() or not anchor.is_file()):
        raise ValueError("共用测试登记处缺失；不能把丢失的记录当作未使用。")
    # The separate anchor detects accidental deletion/replacement of the DB.
    # An operator who can replace BOTH files is outside this trust boundary.
    if initialize and anchor.exists() and not path.exists():
        raise ValueError("测试登记库已丢失；请恢复原库，不能自动重建空记录。")
    # An anchored or existing registry is opened without create permission, so
    # disappearance between the checks above and connect cannot create a new DB.
    mode = "rw" if path.exists() or anchor.exists() or not initialize else "rwc"
    db = sqlite3.connect(path.as_uri() + f"?mode={mode}", uri=True, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.execute("BEGIN IMMEDIATE")
        if initialize:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
            if tables and "metadata" not in tables:
                raise ValueError("此文件不是测试登记库；不会写入或初始化其他数据库。")
            db.execute("CREATE TABLE IF NOT EXISTS metadata (id TEXT NOT NULL)")
            row = db.execute("SELECT id FROM metadata").fetchone()
            if row is None:
                if anchor.exists():
                    raise ValueError("测试登记库身份缺失，禁止重新初始化。")
                identity = str(uuid.uuid4())
                db.execute("INSERT INTO metadata VALUES (?)", (identity,))
                # An interrupted initialization fails closed and needs recovery.
                with anchor.open("x", encoding="utf-8") as stream:
                    stream.write(identity)
            db.execute("CREATE TABLE IF NOT EXISTS datasets (id TEXT PRIMARY KEY, lineage TEXT NOT NULL, samples INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS samples (dataset TEXT, asset TEXT, start TEXT, end TEXT, PRIMARY KEY(dataset,asset,start,end))")
            db.execute("CREATE INDEX IF NOT EXISTS sample_lookup ON samples(asset,start,end)")
            db.execute("CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, dataset TEXT NOT NULL, binding TEXT NOT NULL, status TEXT NOT NULL, created TEXT NOT NULL, result_hash TEXT, conflict TEXT)")
            db.execute("CREATE INDEX IF NOT EXISTS request_dataset ON requests(dataset,status)")
        row = db.execute("SELECT id FROM metadata").fetchone()
        if not row or not anchor.is_file() or anchor.read_text(encoding="utf-8") != row["id"] or (expected and expected != row["id"]):
            raise ValueError("测试登记处身份不匹配，禁止继续。")
        yield db, row["id"]
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def register(lineage, samples, path=None):
    """Register canonical (asset, label_start, label_end) tuples, not file bytes.

    Lineage and asset aliases must be normalized by the trusted data custodian.
    Inclusive intervals deliberately reject even a shared boundary observation.
    """
    if not isinstance(lineage, str) or not lineage.strip():
        raise ValueError("必须提供由数据保管方确定的来源标识。")
    canonical = set()
    for asset, start, end in samples:
        if not isinstance(asset, str) or not asset.strip():
            raise ValueError("样本缺少资产标识。")
        start, end = date.fromisoformat(str(start)).isoformat(), date.fromisoformat(str(end)).isoformat()
        if start > end:
            raise ValueError("样本结束时间早于开始时间。")
        canonical.add((asset.strip(), start, end))
    if not canonical:
        raise ValueError("不能登记空测试集。")
    rows = sorted(canonical)
    lineage = lineage.strip()
    dataset = _hash([lineage, rows])
    path = Path(path or default_path()).resolve()
    with _db(path, initialize=True) as (db, identity):
        db.execute("INSERT OR IGNORE INTO datasets VALUES (?,?,?)", (dataset, lineage, len(rows)))
        db.executemany("INSERT OR IGNORE INTO samples VALUES (?,?,?,?)", [(dataset, *row) for row in rows])
    return {"path": str(path), "registry_id": identity, "dataset_id": dataset,
            "sample_count": len(rows), "policy": "reject-any-overlap-v1"}


def _conflict(db, dataset):
    if not db.execute("SELECT 1 FROM requests WHERE status IN ('reserved','completed','failed') LIMIT 1").fetchone():
        return None
    exact = db.execute("SELECT id FROM requests WHERE dataset=? AND status IN ('reserved','completed','failed') LIMIT 1", (dataset,)).fetchone()
    if exact:
        return exact
    return db.execute("""SELECT r.id FROM samples a
        JOIN samples b ON a.asset=b.asset AND a.start<=b.end AND b.start<=a.end
        JOIN datasets da ON da.id=a.dataset JOIN datasets dbb ON dbb.id=b.dataset
        JOIN requests r ON r.dataset=b.dataset
        WHERE a.dataset=? AND da.lineage=dbb.lineage AND r.status IN ('reserved','completed','failed')
        LIMIT 1""", (dataset,)).fetchone()


def status(ref):
    with _db(ref["path"], ref["registry_id"]) as (db, _):
        if not db.execute("SELECT 1 FROM datasets WHERE id=?", (ref["dataset_id"],)).fetchone():
            raise ValueError("登记处没有该测试集。")
        conflict = _conflict(db, ref["dataset_id"])
        return {"available": conflict is None, "conflict_request": conflict["id"] if conflict else None,
                "registry_id": ref["registry_id"], "dataset_id": ref["dataset_id"]}


def claim(ref, request_id, study_id, frozen_hash, reviewer):
    """Atomically consume BEFORE evaluating; replay returns receipt, never a lease."""
    if not all(isinstance(v, str) and v.strip() for v in (request_id, study_id, frozen_hash, reviewer)):
        raise ValueError("测试申请必须绑定研究、冻结版本与接收结果的人。")
    binding = _json({"study_id": study_id, "frozen_hash": frozen_hash, "reviewer": reviewer,
                     "dataset_id": ref["dataset_id"], "policy": ref["policy"]})
    with _db(ref["path"], ref["registry_id"]) as (db, _):
        previous = db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
        if previous:
            if previous["binding"] != binding:
                raise ValueError("同一测试申请不能更换研究、候选或结果接收人。")
            return {**dict(previous), "granted": False, "replayed": True}
        if ref["policy"] != "reject-any-overlap-v1" or not db.execute("SELECT 1 FROM datasets WHERE id=?", (ref["dataset_id"],)).fetchone():
            raise ValueError("未知测试集或使用政策。")
        conflict = _conflict(db, ref["dataset_id"])
        state = "denied" if conflict else "reserved"
        db.execute("INSERT INTO requests VALUES (?,?,?,?,?,?,?)", (request_id, ref["dataset_id"], binding,
                   state, datetime.now(timezone.utc).isoformat(), None, conflict["id"] if conflict else None))
        receipt = dict(db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone())
    return {**receipt, "granted": not bool(conflict), "replayed": False}


def finish(ref, request_id, result_hash=None):
    with _db(ref["path"], ref["registry_id"]) as (db, _):
        row = db.execute("SELECT * FROM requests WHERE id=? AND dataset=?", (request_id, ref["dataset_id"])).fetchone()
        desired = "completed" if result_hash else "failed"
        if row is None or row["status"] not in ("reserved", desired):
            raise ValueError("没有可完成的测试申请。")
        if row["status"] == desired and row["result_hash"] != result_hash:
            raise ValueError("已完成测试不能替换结果。")
        db.execute("UPDATE requests SET status=?,result_hash=? WHERE id=?", (desired, result_hash, request_id))


def verify(ref, request_id, study_id, frozen_hash, reviewer, result_hash):
    with _db(ref["path"], ref["registry_id"]) as (db, _):
        row = db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
        binding = {"study_id": study_id, "frozen_hash": frozen_hash, "reviewer": reviewer,
                   "dataset_id": ref["dataset_id"], "policy": ref["policy"]}
        return bool(row and row["status"] == "completed" and row["dataset"] == ref["dataset_id"]
                    and row["binding"] == _json(binding) and row["result_hash"] == result_hash)
