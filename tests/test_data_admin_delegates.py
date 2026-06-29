from __future__ import annotations

from data_loader import DataStore


def _store_with_legacy_relics() -> DataStore:
    store = DataStore()
    store.relics = [
        {
            "archive_code": "A001",
            "name": "Alpha Hall",
            "category_main": "0300",
            "heritage_level": "5",
            "survey_type": "2",
            "center_lng": 120.1,
            "center_lat": 30.1,
            "township": "Town A",
            "village": "Village A",
            "era": "Ming",
            "era_stats": "Ming",
            "has_3d": True,
            "has_boundary": True,
            "photo_count": 2,
            "drawing_count": 1,
        },
        {
            "archive_code": "B002",
            "name": "Beta Site",
            "category_main": "0100",
            "heritage_level": "4",
            "survey_type": "12",
            "center_lng": 121.1,
            "center_lat": 31.1,
            "township": "Town B",
            "has_3d": False,
            "has_boundary": False,
            "photo_count": 0,
            "drawing_count": 0,
        },
    ]
    return store


def test_admin_list_relics_uses_legacy_delegate_when_db_disabled():
    store = _store_with_legacy_relics()

    result = store.admin_list_relics(
        search="Alpha",
        categories=["0300"],
        ranks=["5"],
        search_type="2",
    )

    assert result["total"] == 1
    assert result["data"][0]["code"] == "A001"
    assert result["data"][0]["has_photo"] is True


def test_admin_export_relics_uses_legacy_delegate_when_db_disabled():
    store = _store_with_legacy_relics()

    rows = list(store.admin_export_relics(township="Town B"))

    assert len(rows) == 1
    assert rows[0]["code"] == "B002"


def test_admin_stats_overview_uses_legacy_delegate_when_db_disabled():
    store = _store_with_legacy_relics()

    stats = store.admin_stats_overview()

    assert stats["totals"]["total"] == 2
    assert stats["totals"]["has_3d"] == 1
    assert stats["totals"]["has_photo"] == 1
    assert stats["by_township_top"][0] == {"name": "Town A", "count": 1}


def test_facet_counts_legacy_when_db_disabled():
    store = _store_with_legacy_relics()
    res = store.facet_counts()

    assert res["total"] == 2
    cat = {f["code"]: f["count"] for f in res["facets"]["category"]}
    assert cat["0300"] == 1 and cat["0100"] == 1
    assert len(res["facets"]["category"]) == 6          # 国标全集 0 填充
    twn = {f["name"]: f["count"] for f in res["facets"]["township"]}
    assert twn == {"Town A": 1, "Town B": 1}


def test_facet_counts_legacy_respects_filter():
    store = _store_with_legacy_relics()
    res = store.facet_counts(categories=["0300"])
    assert res["total"] == 1
    cat = {f["code"]: f["count"] for f in res["facets"]["category"]}
    assert cat["0300"] == 1 and cat["0100"] == 0
