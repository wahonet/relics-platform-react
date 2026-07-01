"""step07_build_db 建库回归测试(P2-b 等)。

用 tmp 目录跑真正的 build_db,验证 has_photo 双向同步:
photos 表有记录 → 1;JSON 标了 photo_count 但无照片入库 → 0。

需要 pyyaml(step07 import 链经 _common)。注:step07 在 import 时会通过
get_logger 往 data/output/logs 写一行日志(gitignored),属既有副作用。
"""
from __future__ import annotations

import json
import sqlite3

import step07_build_db as step07


def _write_dataset(ds_dir, relics, photo_index_csv: str = ""):
    ds_dir.mkdir(parents=True, exist_ok=True)
    (ds_dir / "relics_full.json").write_text(
        json.dumps(relics, ensure_ascii=False), encoding="utf-8"
    )
    if photo_index_csv:
        (ds_dir / "photo_index.csv").write_text(photo_index_csv, encoding="utf-8-sig")


def test_refresh_has_photo_is_two_way(tmp_path):
    ds = tmp_path / "dataset"
    relics = [
        {"archive_code": "P001", "name": "确有照片",
         "center_lng": 116.5, "center_lat": 35.4, "photo_count": 2},
        {"archive_code": "P002", "name": "标了有照片但实际没入库",
         "center_lng": 116.6, "center_lat": 35.5, "photo_count": 3},
    ]
    # 只有 P001 在 photo_index 里真有照片;P002 虽 photo_count=3 但无照片记录。
    _write_dataset(ds, relics, "archive_code,path\nP001,P001/a.jpg\n")

    step07.build_db(ds / "relics.db", ds, tmp_path / "no_pdf_dir")

    conn = sqlite3.connect(str(ds / "relics.db"))
    conn.row_factory = sqlite3.Row
    try:
        rows = {r["code"]: r for r in conn.execute(
            "SELECT code, has_photo, photo_count FROM relics ORDER BY code")}
    finally:
        conn.close()

    assert rows["P001"]["has_photo"] == 1          # 有照片 → 1
    assert rows["P002"]["has_photo"] == 0          # 无照片入库 → 双向置 0(旧实现会是 1)
    assert rows["P002"]["photo_count"] == 3        # photo_count 仍保留 JSON 上报值


def test_build_db_indexes_are_queryable(tmp_path):
    """顺带冒烟:R-Tree 与 FTS5 建好且可查(名字给足 3 字走 trigram)。"""
    ds = tmp_path / "dataset"
    _write_dataset(ds, [
        {"archive_code": "Q001", "name": "城关镇古塔",
         "center_lng": 117.0, "center_lat": 36.0, "photo_count": 0},
    ])
    step07.build_db(ds / "relics.db", ds, tmp_path / "nope")

    conn = sqlite3.connect(str(ds / "relics.db"))
    try:
        # R-Tree:包含该点的 bbox 能命中。
        n_rtree = conn.execute(
            "SELECT COUNT(*) FROM relics_rtree "
            "WHERE min_lng >= 116.9 AND max_lng <= 117.1"
        ).fetchone()[0]
        assert n_rtree == 1
        # FTS5 trigram:子串能命中。
        hit = conn.execute(
            'SELECT code FROM relics_fts WHERE relics_fts MATCH ?', ('"关镇古"',)
        ).fetchone()
        assert hit is not None and hit[0] == "Q001"
    finally:
        conn.close()


def test_build_db_accepts_real_step03_relative_path(tmp_path):
    """P0-01:step03 真实产出的 photo_index.csv 列名是 relative_path,
    step07 必须据此把照片灌进库(旧实现只读 path → 真实管线照片全丢)。"""
    ds = tmp_path / "dataset"
    relics = [
        {"archive_code": "P001", "name": "确有照片",
         "center_lng": 116.5, "center_lat": 35.4, "photo_count": 1},
    ]
    _write_dataset(
        ds, relics,
        "archive_code,relative_path,photo_no,photo_name\n"
        "P001,P001/a.jpg,Z001,正立面\n",
    )

    step07.build_db(ds / "relics.db", ds, tmp_path / "no_pdf_dir")

    conn = sqlite3.connect(str(ds / "relics.db"))
    try:
        assert conn.execute("SELECT COUNT(*) FROM photos").fetchone()[0] == 1
        assert conn.execute(
            "SELECT has_photo FROM relics WHERE code='P001'"
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_build_db_accepts_real_step04_relative_path(tmp_path):
    """P0-01:step04 真实产出的 drawing_index.csv 列名同样是 relative_path。"""
    ds = tmp_path / "dataset"
    relics = [
        {"archive_code": "D001", "name": "有图纸",
         "center_lng": 116.5, "center_lat": 35.4},
    ]
    _write_dataset(ds, relics)
    (ds / "drawing_index.csv").write_text(
        "archive_code,relative_path,drawing_no\nD001,D001/t1.jpg,T001\n",
        encoding="utf-8-sig",
    )

    step07.build_db(ds / "relics.db", ds, tmp_path / "no_pdf_dir")

    conn = sqlite3.connect(str(ds / "relics.db"))
    try:
        assert conn.execute("SELECT COUNT(*) FROM drawings").fetchone()[0] == 1
    finally:
        conn.close()


def test_build_db_failed_build_keeps_existing_db(tmp_path, monkeypatch):
    """P0-02:构建中途失败时,旧库必须原样保留,不能被半成品/空库覆盖。"""
    ds = tmp_path / "dataset"
    relics = [
        {"archive_code": "OLD01", "name": "旧文物",
         "center_lng": 116.5, "center_lat": 35.4},
    ]
    _write_dataset(ds, relics)

    # 1) 先成功建一次,这就是要被保护的“旧库”。
    step07.build_db(ds / "relics.db", ds, tmp_path / "no_pdf_dir")
    assert (ds / "relics.db").exists()

    # 2) 注入失败:让 _insert_relics 在重建时抛错。
    def boom(*args, **kwargs):
        raise RuntimeError("模拟建库中途失败")

    monkeypatch.setattr(step07, "_insert_relics", boom)

    # 3) 重建应当抛错,且不留下 .tmp。
    try:
        step07.build_db(ds / "relics.db", ds, tmp_path / "no_pdf_dir")
        raised = False
    except RuntimeError:
        raised = True
    assert raised
    assert not list(ds.glob("*.tmp"))

    # 4) 旧库仍在,且旧数据完整(OLD01 还在,没有被空库覆盖)。
    conn = sqlite3.connect(str(ds / "relics.db"))
    try:
        row = conn.execute(
            "SELECT code FROM relics WHERE code='OLD01'"
        ).fetchone()
        assert row is not None and row[0] == "OLD01"
    finally:
        conn.close()
