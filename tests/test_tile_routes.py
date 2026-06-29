import tile_routes


def test_parse_zoom_list_filters_out_of_range_values():
    assert tile_routes._parse_zoom_list("12,13,1415,16") == [12, 13, 16]
    assert tile_routes._parse_zoom_list("0,1,17,18,abc") == [1, 17]


def test_tiles_for_bounds_rejects_invalid_zoom_without_overflow():
    assert tile_routes._tiles_for_bounds(116.0, 35.0, 117.0, 36.0, 1415) == []


def test_parse_provider_list_deduplicates_and_filters_unknowns():
    assert tile_routes._parse_provider_list("arcgis_sat,bad,osm,arcgis_sat") == [
        "arcgis_sat",
        "osm",
    ]


# ── 磁盘配额守护(P2-c)────────────────────────────────────────
def test_download_allowed_is_pure_threshold():
    assert tile_routes._download_allowed(1000, 500) is True
    assert tile_routes._download_allowed(500, 500) is True    # 等于阈值放行
    assert tile_routes._download_allowed(499, 500) is False


def test_min_free_bytes_reads_config(monkeypatch):
    monkeypatch.setattr(tile_routes, "_get_config", lambda: {"tiles": {"min_free_disk_mb": 200}})
    assert tile_routes._min_free_bytes() == 200 * 1024 * 1024

    monkeypatch.setattr(tile_routes, "_get_config", lambda: {})
    assert tile_routes._min_free_bytes() == 500 * 1024 * 1024  # 默认 500MB

    monkeypatch.setattr(tile_routes, "_get_config", lambda: {"tiles": {"min_free_disk_mb": "abc"}})
    assert tile_routes._min_free_bytes() == 500 * 1024 * 1024  # 垃圾值回退默认


def test_free_bytes_int_and_safe_fallback(monkeypatch):
    assert isinstance(tile_routes._free_bytes(), int)

    def _boom(_):
        raise OSError("disk_usage unavailable")

    monkeypatch.setattr(tile_routes.shutil, "disk_usage", _boom)
    assert tile_routes._free_bytes() == (1 << 62)  # 取不到时放行,不误伤
