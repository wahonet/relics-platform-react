from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import HTTPException

from _common import get_paths

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"

SCRIPTS: dict[str, Path] = {
    "step01_convert_docs": SCRIPTS_DIR / "step01_convert_docs.py",
    "step02_build_dataset": SCRIPTS_DIR / "step02_build_dataset.py",
    "step03_extract_photos": SCRIPTS_DIR / "step03_extract_photos.py",
    "step04_extract_drawings": SCRIPTS_DIR / "step04_extract_drawings.py",
    "step05_convert_worklogs": SCRIPTS_DIR / "step05_convert_worklogs.py",
    "step06_prepare_boundaries": SCRIPTS_DIR / "step06_prepare_boundaries.py",
    "step07_build_db": SCRIPTS_DIR / "step07_build_db.py",
    "run_pipeline": SCRIPTS_DIR / "run_pipeline.py",
}

SCRIPT_ALIAS: dict[str, str] = {
    "process_docs": "step01_convert_docs",
    "build_dataset": "step02_build_dataset",
    "extract_photos": "step03_extract_photos",
    "extract_drawings": "step04_extract_drawings",
    "convert_worklogs": "step05_convert_worklogs",
    "prepare_boundaries": "step06_prepare_boundaries",
    "build_db": "step07_build_db",
}

tasks: dict[str, dict] = {}

# 已结束任务(done/error/skipped 等)在内存中保留的上限;运行中的不计入也不裁剪。
_MAX_FINISHED_TASKS = 200


def _prune_tasks() -> None:
    """裁剪 tasks 历史:running/starting 全保留,已结束的只留最近 _MAX_FINISHED_TASKS 条。

    仅在事件循环线程(start_script_task)中调用,故对 key 集合的增删不会与异步端点的
    遍历交错;执行线程(run_script_sync)只更新已存在条目的值,不增删 key。
    """
    finished = [
        (tid, t) for tid, t in tasks.items()
        if t.get("status") not in ("starting", "running")
    ]
    excess = len(finished) - _MAX_FINISHED_TASKS
    if excess <= 0:
        return
    finished.sort(key=lambda kv: kv[1].get("started", ""))
    for tid, _t in finished[:excess]:
        tasks.pop(tid, None)


def resolve_script(name: str) -> str:
    if name in SCRIPTS:
        return name
    if name in SCRIPT_ALIAS:
        return SCRIPT_ALIAS[name]
    raise HTTPException(400, f"Unknown script: {name}")


def last_task_for(script_name: str) -> Optional[dict]:
    latest: Optional[tuple[str, dict]] = None
    for tid, task in tasks.items():
        if task["script"] == script_name:
            if latest is None or task["started"] > latest[1]["started"]:
                latest = (tid, task)
    if not latest:
        return None
    _, task = latest
    return {
        "status": task["status"],
        "started": task["started"],
        "finished": task.get("finished"),
    }


def run_script_sync(script_path: str, task_id: str, extra_env: Optional[dict] = None) -> None:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    if extra_env:
        env.update(extra_env)

    tasks[task_id]["status"] = "running"
    try:
        proc = subprocess.Popen(
            [sys.executable, script_path],
            cwd=str(get_paths().root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        lines: list[str] = []
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line.rstrip("\n"))
            tasks[task_id]["log"] = lines[-300:]
        proc.wait()
        tasks[task_id]["returncode"] = proc.returncode
        tasks[task_id]["status"] = "done" if proc.returncode == 0 else "error"
        tasks[task_id]["finished"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        tasks[task_id]["status"] = "error"
        tasks[task_id]["log"] = tasks[task_id].get("log", []) + [f"Exception: {e}"]


def start_script_task(
    script_name: str,
    *,
    extra_env: Optional[dict] = None,
    initial_log: Optional[list[str]] = None,
    extra_fields: Optional[dict] = None,
) -> dict:
    real = resolve_script(script_name)
    for tid, task in tasks.items():
        if task["script"] == real and task["status"] == "running":
            raise HTTPException(409, f"{real} is already running (task={tid})")

    task_id = str(uuid.uuid4())[:8]
    tasks[task_id] = {
        "status": "starting",
        "script": real,
        "started": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "log": initial_log or [],
        "returncode": None,
        **(extra_fields or {}),
    }
    # 限制历史规模,避免长时间运行后 tasks 无界增长(只裁已结束的,不动运行中的)。
    _prune_tasks()

    script_path = str(SCRIPTS[real])
    # 用 get_running_loop():get_event_loop() 在新版 Python 已废弃;本函数必由
    # async 路由调用,运行中的事件循环一定存在。
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, run_script_sync, script_path, task_id, extra_env)
    return {"task_id": task_id, "script": real}

