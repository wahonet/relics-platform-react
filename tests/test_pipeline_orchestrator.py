from __future__ import annotations

import sys
from types import SimpleNamespace

import run_pipeline


def test_pipeline_includes_sqlite_build_step():
    ids = [step["id"] for step in run_pipeline.STEPS]
    assert ids == ["01", "02", "03", "04", "05", "06", "07"]
    assert run_pipeline.STEPS[-1]["script"] == "step07_build_db.py"


def test_select_steps_supports_skip():
    args = SimpleNamespace(only_id=None, from_id=None, to_id=None, skip_ids=["01", "05"])
    selected = run_pipeline._select_steps(args)
    assert [step["id"] for step in selected] == ["02", "03", "04", "06", "07"]


def test_select_steps_supports_range_and_skip():
    args = SimpleNamespace(only_id=None, from_id="03", to_id="07", skip_ids=["06"])
    selected = run_pipeline._select_steps(args)
    assert [step["id"] for step in selected] == ["03", "04", "05", "07"]


def test_select_steps_numeric_compare_with_double_digit_ids(monkeypatch):
    """字符串比较下 '9' <= '10' 为 False;数值比较修正后区间应正确。"""
    steps = [{"id": f"{i:02d}", "script": f"s{i}.py"} for i in range(1, 13)]  # 01..12
    monkeypatch.setattr(run_pipeline, "STEPS", steps)

    args = SimpleNamespace(only_id=None, from_id="9", to_id="11", skip_ids=[])
    selected = [s["id"] for s in run_pipeline._select_steps(args)]
    assert selected == ["09", "10", "11"]  # 含两位 id,且 09 未被错误排除


def test_select_steps_id_is_zero_pad_insensitive(monkeypatch):
    steps = [{"id": f"{i:02d}", "script": f"s{i}.py"} for i in range(1, 13)]
    monkeypatch.setattr(run_pipeline, "STEPS", steps)

    # only '1' 应等价于 '01';skip '10'(两位)应命中 id '10'。
    only = run_pipeline._select_steps(
        SimpleNamespace(only_id="1", from_id=None, to_id=None, skip_ids=[])
    )
    assert [s["id"] for s in only] == ["01"]

    skipped = run_pipeline._select_steps(
        SimpleNamespace(only_id=None, from_id="08", to_id="12", skip_ids=["10"])
    )
    assert [s["id"] for s in skipped] == ["08", "09", "11", "12"]


def test_dry_run_does_not_require_config(monkeypatch):
    class DummyLogger:
        def info(self, *args, **kwargs):
            pass

        def error(self, *args, **kwargs):
            pass

    def fail_load_config():
        raise AssertionError("dry-run should not load config.yaml")

    monkeypatch.setattr(run_pipeline, "get_logger", lambda _name: DummyLogger())
    monkeypatch.setattr(run_pipeline, "load_config", fail_load_config)
    monkeypatch.setattr(
        run_pipeline,
        "detect_features",
        lambda: SimpleNamespace(
            as_dict={
                "archives": False,
                "worklogs": False,
                "boundaries": False,
                "dem": False,
                "models_3d": False,
            }
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_pipeline.py", "--dry-run", "--skip", "01", "--skip", "05"],
    )

    assert run_pipeline.main() == 0
