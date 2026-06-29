"""admin_task_service 的任务历史 GC 与事件循环用法测试(Bug #5)。

需要 fastapi(HTTPException)+ pyyaml(_common),运行器已装。
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from routers import admin_task_service as ats


@pytest.fixture(autouse=True)
def _clean_tasks():
    ats.tasks.clear()
    yield
    ats.tasks.clear()


def test_prune_caps_finished_but_keeps_running(monkeypatch):
    monkeypatch.setattr(ats, "_MAX_FINISHED_TASKS", 5)
    for i in range(3):
        ats.tasks[f"run{i}"] = {
            "script": "s", "status": "running", "started": f"2026-01-01 00:00:0{i}",
        }
    for i in range(20):
        ats.tasks[f"done{i:02d}"] = {
            "script": "s", "status": "done", "started": f"2026-01-02 00:{i:02d}:00",
        }

    ats._prune_tasks()

    running = [t for t in ats.tasks.values() if t["status"] == "running"]
    finished = [t for t in ats.tasks.values() if t["status"] != "running"]
    assert len(running) == 3          # 运行中的全保留
    assert len(finished) == 5         # 已结束的截到上限
    assert "done00" not in ats.tasks  # 最旧的被裁掉
    assert "done19" in ats.tasks      # 最近的保留


def test_prune_noop_when_under_cap(monkeypatch):
    monkeypatch.setattr(ats, "_MAX_FINISHED_TASKS", 100)
    for i in range(10):
        ats.tasks[f"done{i}"] = {"script": "s", "status": "done", "started": f"t{i}"}
    ats._prune_tasks()
    assert len(ats.tasks) == 10


def test_start_task_registers_and_409_on_running_duplicate(monkeypatch):
    # 用 no-op 替掉真正的子进程执行,只验证调度/登记/去重逻辑。
    monkeypatch.setattr(ats, "run_script_sync", lambda *a, **k: None)

    async def go():
        first = ats.start_script_task("step07_build_db")
        # 模拟首个任务已进入 running,再次启动同脚本应 409。
        ats.tasks[first["task_id"]]["status"] = "running"
        err = None
        try:
            ats.start_script_task("step07_build_db")
        except HTTPException as e:
            err = e
        return first, err

    first, err = asyncio.run(go())
    assert first["script"] == "step07_build_db"
    assert first["task_id"] in ats.tasks         # 已登记
    assert err is not None and err.status_code == 409  # 运行中重复 → 409
