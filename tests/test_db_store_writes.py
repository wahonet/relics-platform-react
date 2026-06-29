"""DataStore（DB 模式)写后读回归测试。

复现并守护两个后台写路径 bug:

Bug #1 — search_fulltext 之前用 `relics_fts.rowid = relics_rtree_map.id_int`
         连接。两条 rowid 序列只在 step07 建库时对齐(1..N);后台改一次名,
         _fts_upsert 的 DELETE+INSERT 会让 fts.rowid 重新分配,连接错位,
         被编辑的文物从此搜不到(或搜出别人)。修复:改按 relics.code 连接。

Bug #2 — get_relic_full 之前加了 @lru_cache 且写操作后从不失效,导致编辑后
         详情接口仍返回旧值。修复:去掉缓存。

为了不依赖 pyyaml / fastapi / numpy,这里直接用 sqlite3 内联建一个 mini 库,
schema 与 rowid 对齐方式都照搬 step07_build_db,只需 pytest + 标准库即可跑。
"""
from __future__ import annotations

import sqlite3
import time
import uuid

import pytest

from data_loader import DataStore

# step07_build_db.SCHEMA_SQL 的最小子集 —— 只保留 DataStore 会触及的表。
_SCHEMA = """
CREATE TABLE relics (
    id TEXT PRIMARY KEY, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
    category TEXT NOT NULL, rank TEXT NOT NULL, search_type TEXT,
    lng REAL NOT NULL, lat REAL NOT NULL, alt REAL,
    township TEXT, village TEXT, address TEXT, era TEXT, era_stats TEXT,
    has_3d INTEGER DEFAULT 0, has_pdf INTEGER DEFAULT 0, has_photo INTEGER DEFAULT 0,
    has_boundary INTEGER DEFAULT 0, photo_count INTEGER DEFAULT 0, drawing_count INTEGER DEFAULT 0,
    brief TEXT, extra_json TEXT, status INTEGER DEFAULT 1, version INTEGER DEFAULT 1,
    created_at INTEGER, updated_at INTEGER
);
CREATE VIRTUAL TABLE relics_rtree USING rtree(id_int, min_lng, max_lng, min_lat, max_lat);
CREATE TABLE relics_rtree_map (id_int INTEGER PRIMARY KEY, relic_id TEXT UNIQUE NOT NULL);
CREATE VIRTUAL TABLE relics_fts USING fts5(
    code, name, brief, era, township, village, tokenize="trigram"
);
CREATE TABLE photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT, relic_code TEXT NOT NULL, path TEXT NOT NULL,
    thumb_path TEXT, taken_at INTEGER, UNIQUE(relic_code, path)
);
CREATE TABLE drawings (
    id INTEGER PRIMARY KEY AUTOINCREMENT, relic_code TEXT NOT NULL, path TEXT NOT NULL,
    UNIQUE(relic_code, path)
);
CREATE TABLE polygons (relic_code TEXT PRIMARY KEY, geom_geojson TEXT NOT NULL);
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT, action TEXT, relic_code TEXT,
    before_json TEXT, after_json TEXT, ts INTEGER
);
"""

# code, name, category(国标), lng, lat —— 名字给足 3+ 字以便走 FTS5 trigram。
_ROWS = [
    ("A001", "甲村古桥梁", "0300", 116.50, 35.40),
    ("A002", "乙村古遗址", "0100", 116.60, 35.50),
    ("A003", "丙村石刻群", "0400", 116.70, 35.30),
]


def _build_tiny_db(db_path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(_SCHEMA)
        now = int(time.time())
        for idx, (code, name, cat, lng, lat) in enumerate(_ROWS, start=1):
            rid = str(uuid.uuid4())
            # brief 故意与 name 无公共子串:这样"改名后用旧名搜应搜不到"才是
            # 有效断言(否则旧名仍残留在 brief 里会一直命中)。
            brief = "暂无简介，待补充。"
            conn.execute(
                "INSERT INTO relics (id, code, name, category, rank, search_type, "
                "lng, lat, alt, brief, status, version, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, '5', '2', ?, ?, 0, ?, 1, 1, ?, ?)",
                (rid, code, name, cat, lng, lat, brief, now, now),
            )
            # 建库时刻意让 rtree.id_int == fts.rowid == idx —— 这正是 step07
            # 的做法,也正是运行时 upsert 之后会被打破的隐式不变量。
            conn.execute(
                "INSERT INTO relics_rtree_map (id_int, relic_id) VALUES (?, ?)", (idx, rid)
            )
            conn.execute(
                "INSERT INTO relics_rtree (id_int, min_lng, max_lng, min_lat, max_lat) "
                "VALUES (?, ?, ?, ?, ?)",
                (idx, lng, lng, lat, lat),
            )
            conn.execute(
                "INSERT INTO relics_fts (rowid, code, name, brief, era, township, village) "
                "VALUES (?, ?, ?, ?, '', '', '')",
                (idx, code, name, brief),
            )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture()
def store(tmp_path):
    _build_tiny_db(tmp_path / "relics.db")
    s = DataStore()
    s.load(str(tmp_path))
    assert s._use_db is True
    return s


def test_fts_search_survives_admin_rename(store):
    """改名后,文物仍能按新名字被全文搜索到(Bug #1 回归)。"""
    # 基线:建库后按原名(trigram,>=3 字)能搜到。
    assert [h["code"] for h in store.search_fulltext("甲村古")] == ["A001"]

    # 后台改名 —— 触发 _fts_upsert(DELETE+INSERT)。
    store.update_relic("A001", {"name": "甲村新桥梁"}, expected_version=1, actor="t")

    # 必须能按新名字搜到。修复前(按 rowid=id_int 连接)这里会得到 []。
    assert [h["code"] for h in store.search_fulltext("新桥梁")] == ["A001"]
    # 旧名字应当搜不到了(sanity)。
    assert store.search_fulltext("甲村古") == []


def test_get_relic_full_reflects_update(store):
    """编辑后详情接口返回新值,而非缓存旧值(Bug #2 回归)。"""
    first = store.get_relic_full("A002")
    assert first is not None and first["name"] == "乙村古遗址"

    store.update_relic("A002", {"name": "乙村新遗址"}, expected_version=1, actor="t")

    # 修复前(lru_cache 未失效)这里仍是 "乙村古遗址"。
    again = store.get_relic_full("A002")
    assert again is not None and again["name"] == "乙村新遗址"


def test_get_relic_full_not_caching_missing_then_created(store):
    """先查不存在的 code(返回 None),再创建,应能查到(Bug #2 的 None 缓存面)。"""
    assert store.get_relic_full("Z999") is None
    store.create_relic(
        {"code": "Z999", "name": "丁村新发现", "category": "0100",
         "rank": "5", "lng": 116.55, "lat": 35.45},
        actor="t",
    )
    created = store.get_relic_full("Z999")
    assert created is not None and created["name"] == "丁村新发现"
    # 新建的文物也应可被全文检索(顺带覆盖 create 路径的 FTS)。
    assert [h["code"] for h in store.search_fulltext("丁村新")] == ["Z999"]


# ── P1-1:写路径增量维护内存镜像(不再全表重读)────────────────
def _count_full_reload(store, monkeypatch) -> dict:
    """把 _populate_legacy_from_db 换成只计数的桩,用于断言写路径不再全量重读。"""
    calls = {"n": 0}
    monkeypatch.setattr(
        store, "_populate_legacy_from_db",
        lambda: calls.__setitem__("n", calls["n"] + 1),
    )
    return calls


def test_update_syncs_mirror_without_full_reload(store, monkeypatch):
    calls = _count_full_reload(store, monkeypatch)
    store.update_relic("A001", {"name": "甲村改名桥"}, expected_version=1, actor="t")

    assert calls["n"] == 0  # 关键:不再触发 O(N) 全量重读
    assert store.relics_map["A001"]["name"] == "甲村改名桥"
    assert any(r["archive_code"] == "A001" and r["name"] == "甲村改名桥"
               for r in store.relics)
    summary = {r["archive_code"]: r for r in store.get_relics_summary()}
    assert summary["A001"]["name"] == "甲村改名桥"


def test_create_appends_to_mirror_without_full_reload(store, monkeypatch):
    calls = _count_full_reload(store, monkeypatch)
    store.create_relic(
        {"code": "C003", "name": "新建村遗址", "category": "0100",
         "rank": "5", "lng": 116.9, "lat": 35.6},
        actor="t",
    )
    assert calls["n"] == 0
    assert store.relics_map["C003"]["name"] == "新建村遗址"
    assert any(r["archive_code"] == "C003" for r in store.relics)


def test_delete_removes_from_mirror_without_full_reload(store, monkeypatch):
    calls = _count_full_reload(store, monkeypatch)
    assert "A002" in store.relics_map
    store.delete_relic("A002", actor="t")

    assert calls["n"] == 0
    assert "A002" not in store.relics_map
    assert all(r["archive_code"] != "A002" for r in store.relics)


def test_status_change_syncs_mirror(store):
    """status=0(草稿)从镜像移除,改回 1 重新加入 —— 与“镜像只收录 status=1”一致。"""
    store.update_relic("A003", {"status": 0}, expected_version=1, actor="t")
    assert "A003" not in store.relics_map
    assert all(r["archive_code"] != "A003" for r in store.relics)

    store.update_relic("A003", {"status": 1}, expected_version=2, actor="t")
    assert "A003" in store.relics_map
    assert any(r["archive_code"] == "A003" for r in store.relics)


def test_bulk_update_avoids_full_reload(store, monkeypatch):
    """批量更新不应每条都全量重读(旧实现是 O(N*M))。"""
    calls = _count_full_reload(store, monkeypatch)
    res = store.admin_bulk_update(
        ["A001", "A002", "A003"], {"township": "统一镇"}, actor="t"
    )
    assert res["updated"] == 3
    assert calls["n"] == 0
    for c in ("A001", "A002", "A003"):
        assert store.relics_map[c]["township"] == "统一镇"

