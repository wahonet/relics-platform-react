"""管理后台 API:触发 step 脚本、查任务、上传/即时处理 DOCX、
查看整条数据管线的分步进度与详情。

脚本路径指向 platform/scripts/step0X_*.py,输入输出目录都走
_common.get_paths(),路由里不出现硬编码路径。
"""
from __future__ import annotations

import asyncio
import csv
import json
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _common import get_paths  # noqa: E402
from codes import (  # noqa: E402
    CATEGORY_CODES,
    RANK_CODES,
    SEARCH_TYPE_CODES,
    normalize_category,
    normalize_rank,
    normalize_search_type,
)
from data_loader import store  # noqa: E402

router = APIRouter(prefix="/admin", tags=["管理"])

# 脚本注册表:同时接受 stepNN 完整名称和前端使用的短别名。
SCRIPTS: dict[str, Path] = {
    "step01_convert_docs":       _SCRIPTS_DIR / "step01_convert_docs.py",
    "step02_build_dataset":      _SCRIPTS_DIR / "step02_build_dataset.py",
    "step03_extract_photos":     _SCRIPTS_DIR / "step03_extract_photos.py",
    "step04_extract_drawings":   _SCRIPTS_DIR / "step04_extract_drawings.py",
    "step05_convert_worklogs":   _SCRIPTS_DIR / "step05_convert_worklogs.py",
    "step06_prepare_boundaries": _SCRIPTS_DIR / "step06_prepare_boundaries.py",
    "run_pipeline":              _SCRIPTS_DIR / "run_pipeline.py",
}
SCRIPT_ALIAS: dict[str, str] = {
    "process_docs":     "step01_convert_docs",
    "build_dataset":    "step02_build_dataset",
    "extract_photos":   "step03_extract_photos",
    "extract_drawings": "step04_extract_drawings",
    "convert_worklogs": "step05_convert_worklogs",
    "prepare_boundaries": "step06_prepare_boundaries",
}


def _resolve_script(name: str) -> str:
    """前端可以传短名或 stepNN_xxx,统一解析到真实脚本键。"""
    if name in SCRIPTS:
        return name
    if name in SCRIPT_ALIAS:
        return SCRIPT_ALIAS[name]
    raise HTTPException(400, f"未知脚本: {name}")


# task_id -> {status, script, started, log[], returncode, finished?}
_tasks: dict[str, dict] = {}


# ── 文件统计工具 ────────────────────────────────────────────
def _count_files(d: Path, pattern: str = "*") -> int:
    if not d.exists():
        return 0
    return sum(1 for _ in d.rglob(pattern) if _.is_file())


def _count_docx(d: Path) -> int:
    if not d.exists():
        return 0
    return sum(1 for f in d.rglob("*.docx") if not f.name.startswith("~$"))


def _mtime_str(p: Path) -> Optional[str]:
    if p.exists():
        return datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    return None


def _count_csv_rows(p: Path) -> int:
    if not p.exists():
        return 0
    try:
        with p.open("r", encoding="utf-8-sig") as f:
            return sum(1 for _ in f) - 1  # 减去表头
    except Exception:
        return 0


def _count_json_array(p: Path) -> int:
    if not p.exists():
        return 0
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return len(data) if isinstance(data, list) else 0
    except Exception:
        return 0


def _progress_pct(done: int, total: int) -> float:
    """进度百分比。total=0 但 done>0 时视为 100%(demo/归档场景)。"""
    if total <= 0:
        return 100.0 if done > 0 else 0.0
    return round(min(100.0, done / total * 100), 1)


def _count_geojson_features(p: Path) -> int:
    if not p.exists():
        return 0
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return len(data.get("features", []) or [])
    except Exception:
        return 0


def _last_task_for(script_name: str) -> Optional[dict]:
    """找这个脚本最近一次任务,用于在管线卡片上显示"最近运行时间"。"""
    latest: Optional[tuple[str, dict]] = None
    for tid, t in _tasks.items():
        if t["script"] == script_name:
            if latest is None or t["started"] > latest[1]["started"]:
                latest = (tid, t)
    if not latest:
        return None
    _, t = latest
    return {
        "status": t["status"],
        "started": t["started"],
        "finished": t.get("finished"),
    }


def _township_dirs() -> list[str]:
    """列出 data/input/01_archives/ 下的一级子目录名(视作乡镇)。"""
    ap = get_paths().input_archives
    if not ap.exists():
        return []
    return sorted(d.name for d in ap.iterdir() if d.is_dir())


def _strip_ordinal(name: str) -> str:
    """'01示范街道' -> '示范街道',step02 里保持一致的做法。"""
    return re.sub(r"^[\d_\-\s]+", "", name) or name


# ── 基础状态 API(兼容旧前端) ─────────────────────────────
@router.get("/status")
async def pipeline_status():
    paths = get_paths()
    townships = _township_dirs()

    docx_count = _count_docx(paths.input_archives)
    md_count = _count_files(paths.output_markdown, "*.md")
    photo_count = _count_files(paths.output_photos)
    drawing_count = _count_files(paths.output_drawings)

    master_csv = paths.output_dataset / "relics_master.csv"
    relics_json = paths.output_dataset / "relics_full.json"

    return {
        "townships": townships,
        "docx_count": docx_count,
        "md_count": md_count,
        "photo_count": photo_count,
        "drawing_count": drawing_count,
        "csv_exists": master_csv.exists(),
        "json_exists": relics_json.exists(),
        "csv_mtime": _mtime_str(master_csv),
        "json_mtime": _mtime_str(relics_json),
        "tasks": {
            tid: {"status": t["status"], "script": t["script"], "started": t["started"]}
            for tid, t in _tasks.items()
        },
    }


@router.get("/townships")
async def list_townships():
    paths = get_paths()
    result = []
    for name in _township_dirs():
        inp = paths.input_archives / name
        out = paths.output_markdown / name
        docx_n = sum(1 for f in inp.glob("*.docx") if not f.name.startswith("~$"))
        md_n = sum(1 for _ in out.glob("*.md")) if out.exists() else 0
        result.append({"name": name, "docx_count": docx_n, "md_count": md_n})
    return result


# ── 新:整条管线分步状态 ─────────────────────────────────
@router.get("/pipeline")
async def pipeline_detailed():
    """返回六步管线逐步进度,供后台竖排流程图使用。

    每步包含:
      id / name / icon / desc / flow('输入 → 输出')
      input:  {total, label}
      output: {total, label, extra?}
      progress: 0~100
      pending: 未处理数量(仅当 input/output 可比时)
      runnable: 该步是否可运行(比如 step05 没工作日志会跳过)
      last_run / artifact_mtime
    """
    paths = get_paths()

    # step01: docx -> md  (按 archive_code 一一对应)
    docx_total = _count_docx(paths.input_archives)
    md_total = _count_files(paths.output_markdown, "*.md")
    step01 = {
        "id": "step01_convert_docs",
        "name": "文档结构化提取",
        "icon": "📄",
        "desc": "调用 AI 大模型把 .docx 四普档案规范化为 Markdown",
        "flow": "DOCX → Markdown",
        "input": {"total": docx_total, "label": "docx 档案"},
        "output": {"total": md_total, "label": "markdown 文件"},
        "pending": max(0, docx_total - md_total),
        # 如果 input 为空但 output 已有产物(典型:demo 数据或仅随仓库携带 md),视为 100%
        "progress": _progress_pct(md_total, docx_total),
        "runnable": docx_total > 0,
        "last_run": _last_task_for("step01_convert_docs"),
        "artifact_mtime": _mtime_str(paths.output_markdown),
    }

    # step02: md -> dataset  (单次全量,csv 存在即视为 100%)
    master_csv = paths.output_dataset / "relics_master.csv"
    relics_json = paths.output_dataset / "relics_full.json"
    points_geo = paths.output_dataset / "relics_points.geojson"
    polygons_geo = paths.output_dataset / "relics_polygons.geojson"
    csv_rows = _count_csv_rows(master_csv)
    step02 = {
        "id": "step02_build_dataset",
        "name": "数据集生成",
        "icon": "📊",
        "desc": "汇总 Markdown → 结构化 CSV / JSON / GeoJSON,生成统计表与风险打分",
        "flow": "Markdown → Dataset",
        "input": {"total": md_total, "label": "markdown 文件"},
        "output": {
            "total": csv_rows,
            "label": "文物记录",
            "extra": {
                "relics_master.csv": csv_rows,
                "relics_points.geojson": _count_geojson_features(points_geo),
                "relics_polygons.geojson": _count_geojson_features(polygons_geo),
                "relics_full.json": _count_json_array(relics_json),
            },
        },
        "pending": max(0, md_total - csv_rows) if master_csv.exists() else md_total,
        "progress": round(csv_rows / md_total * 100, 1) if md_total else (100.0 if master_csv.exists() else 0.0),
        "runnable": md_total > 0,
        "last_run": _last_task_for("step02_build_dataset"),
        "artifact_mtime": _mtime_str(master_csv),
    }

    # step03: docx -> photos  (按有索引记录的 archive_code 计完成)
    photo_index = paths.output_dataset / "photo_index.csv"
    photo_covered = _codes_in_index(photo_index)
    step03 = {
        "id": "step03_extract_photos",
        "name": "照片提取",
        "icon": "📷",
        "desc": "从 .docx 中按顺序抽取照片,生成 photo_index 供前端调取",
        "flow": "DOCX → 照片库",
        "input": {"total": docx_total, "label": "docx 档案"},
        "output": {
            "total": len(photo_covered),
            "label": "条档案已抽图",
            "extra": {"照片总数": _count_files(paths.output_photos)},
        },
        "pending": max(0, docx_total - len(photo_covered)),
        "progress": _progress_pct(len(photo_covered), docx_total),
        "runnable": docx_total > 0,
        "last_run": _last_task_for("step03_extract_photos"),
        "artifact_mtime": _mtime_str(photo_index),
    }

    # step04: docx -> drawings
    drawing_index = paths.output_dataset / "drawing_index.csv"
    drawing_covered = _codes_in_index(drawing_index)
    step04 = {
        "id": "step04_extract_drawings",
        "name": "图纸提取",
        "icon": "📐",
        "desc": "从 .docx 中抽取图纸,生成 drawing_index 供前端调取",
        "flow": "DOCX → 图纸库",
        "input": {"total": docx_total, "label": "docx 档案"},
        "output": {
            "total": len(drawing_covered),
            "label": "条档案已抽图",
            "extra": {"图纸总数": _count_files(paths.output_drawings)},
        },
        "pending": max(0, docx_total - len(drawing_covered)),
        "progress": _progress_pct(len(drawing_covered), docx_total),
        "runnable": docx_total > 0,
        "last_run": _last_task_for("step04_extract_drawings"),
        "artifact_mtime": _mtime_str(drawing_index),
    }

    # step05: worklog xlsx -> pdf  (可选,无数据时跳过)
    worklog_xlsx = _count_files(paths.input_worklogs, "*.xlsx") + _count_files(paths.input_worklogs, "*.xls")
    worklog_pdf = _count_files(paths.output_worklogs, "*.pdf")
    step05 = {
        "id": "step05_convert_worklogs",
        "name": "工作日志转 PDF",
        "icon": "📋",
        "desc": "把外业日志 Excel 按天排版成 A4 PDF,供日志查看器嵌入",
        "flow": "Excel → PDF",
        "input": {"total": worklog_xlsx, "label": "日志表"},
        "output": {"total": worklog_pdf, "label": "日志 PDF"},
        "pending": max(0, worklog_xlsx - worklog_pdf),
        "progress": _progress_pct(worklog_pdf, worklog_xlsx),
        "runnable": worklog_xlsx > 0,
        "optional": True,
        "last_run": _last_task_for("step05_convert_worklogs"),
        "artifact_mtime": _mtime_str(paths.output_worklogs),
    }

    # step06: boundaries shp -> geojson
    shp_total = _count_files(paths.input_boundaries, "*.shp") + _count_files(paths.input_boundaries, "*.geojson")
    b_county = paths.output_boundaries / "county.geojson"
    b_town = paths.output_boundaries / "townships.geojson"
    b_village = paths.output_boundaries / "villages.geojson"
    boundary_out = sum(1 for p in (b_county, b_town, b_village) if p.exists())
    step06 = {
        "id": "step06_prepare_boundaries",
        "name": "行政边界处理",
        "icon": "🗺️",
        "desc": "把 Shapefile / GeoJSON 反投影到 WGS-84,并切分成县/镇/村三级",
        "flow": "SHP → WGS-84 GeoJSON",
        "input": {"total": shp_total, "label": "shp/geojson 原始"},
        "output": {
            "total": boundary_out,
            "label": "边界层",
            "extra": {
                "county.geojson": _count_geojson_features(b_county),
                "townships.geojson": _count_geojson_features(b_town),
                "villages.geojson": _count_geojson_features(b_village),
            },
        },
        "pending": max(0, 3 - boundary_out),
        "progress": round(boundary_out / 3 * 100, 1),
        "runnable": shp_total > 0,
        "optional": True,
        "last_run": _last_task_for("step06_prepare_boundaries"),
        "artifact_mtime": _mtime_str(paths.output_boundaries),
    }

    return {
        "steps": [step01, step02, step03, step04, step05, step06],
        "tasks": {
            tid: {
                "status": t["status"],
                "script": t["script"],
                "started": t["started"],
                "finished": t.get("finished"),
            }
            for tid, t in _tasks.items()
        },
    }


def _codes_in_index(index_csv: Path) -> set[str]:
    if not index_csv.exists():
        return set()
    codes: set[str] = set()
    try:
        with index_csv.open("r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                code = row.get("archive_code") or row.get("code") or ""
                if code:
                    codes.add(code.strip())
    except Exception:
        pass
    return codes


# ── 新:某一步的明细条目 ─────────────────────────────────
@router.get("/step/{step_id}/items")
async def step_items(step_id: str):
    """返回指定步骤的条目级详情,前端用于"查看详情"折叠区。

    step01/step03/step04 → 按乡镇分组,列出每个 docx 的处理状态
    step02               → 按 archive_code 列出每条文物的生成状态
    step05               → 按 Excel 文件列出转换状态
    step06               → 按边界层(县/镇/村)列出产出状态
    """
    step_id = _resolve_script(step_id)
    paths = get_paths()

    if step_id == "step01_convert_docs":
        return _items_step01(paths)
    if step_id == "step02_build_dataset":
        return _items_step02(paths)
    if step_id == "step03_extract_photos":
        return _items_docx_based(paths, index_name="photo_index.csv")
    if step_id == "step04_extract_drawings":
        return _items_docx_based(paths, index_name="drawing_index.csv")
    if step_id == "step05_convert_worklogs":
        return _items_step05(paths)
    if step_id == "step06_prepare_boundaries":
        return _items_step06(paths)

    raise HTTPException(400, f"暂不支持查看 {step_id} 的详情")


def _items_step01(paths) -> dict:
    groups = []
    for twd in sorted(paths.input_archives.iterdir()) if paths.input_archives.exists() else []:
        if not twd.is_dir():
            continue
        township = _strip_ordinal(twd.name)
        out_dir = paths.output_markdown / twd.name
        if not out_dir.exists():
            out_dir_alt = paths.output_markdown / f"01{township}"
            if out_dir_alt.exists():
                out_dir = out_dir_alt
        md_names = {p.stem.split("_")[-1]: p for p in out_dir.glob("*.md")} if out_dir.exists() else {}
        md_by_full_stem = {p.stem: p for p in out_dir.glob("*.md")} if out_dir.exists() else {}
        items = []
        for docx in sorted(twd.glob("*.docx")):
            if docx.name.startswith("~$"):
                continue
            stem = docx.stem
            # md 一般命名为 <archive_code>_<name>_<ts>.md 或 <stem>_*.md
            out_md = None
            for md in md_by_full_stem.values():
                if md.stem.startswith(stem) or stem in md.stem:
                    out_md = md
                    break
            done = out_md is not None
            items.append({
                "id": stem,
                "name": docx.name,
                "status": "done" if done else "pending",
                "input_size_kb": round(docx.stat().st_size / 1024, 1),
                "output": out_md.name if out_md else None,
                "output_size_kb": round(out_md.stat().st_size / 1024, 1) if out_md else 0,
                "output_mtime": _mtime_str(out_md) if out_md else None,
            })
        done_n = sum(1 for i in items if i["status"] == "done")
        groups.append({
            "name": township,
            "total": len(items),
            "done": done_n,
            "pending": len(items) - done_n,
            "items": items,
        })
    return {"step": "step01_convert_docs", "groups": groups}


def _items_step02(paths) -> dict:
    master_csv = paths.output_dataset / "relics_master.csv"
    if not master_csv.exists():
        return {"step": "step02_build_dataset", "groups": []}
    # 从 md 目录统计输入文件总数,从 csv 读出已生成的记录
    md_by_stem: dict[str, Path] = {}
    if paths.output_markdown.exists():
        for md in paths.output_markdown.rglob("*.md"):
            md_by_stem[md.stem] = md

    records: list[dict] = []
    with master_csv.open("r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            records.append(row)

    # 按乡镇分组
    groups_map: dict[str, list[dict]] = {}
    for r in records:
        twp = r.get("township") or "未分类"
        groups_map.setdefault(twp, []).append({
            "id": r.get("archive_code", ""),
            "name": r.get("name", ""),
            "status": "done",
            "category": r.get("category_main", ""),
            "era_stats": r.get("era_stats", ""),
            "condition": r.get("condition_level", ""),
            "risk_score": r.get("risk_score", ""),
            "has_boundary": r.get("has_boundary", "") in ("True", "true", "1"),
            "source_file": r.get("source_file", ""),
        })

    groups = []
    for name, items in sorted(groups_map.items()):
        groups.append({
            "name": name,
            "total": len(items),
            "done": len(items),
            "pending": 0,
            "items": items,
        })
    return {"step": "step02_build_dataset", "groups": groups}


def _items_docx_based(paths, index_name: str) -> dict:
    """step03 / step04:按乡镇列出 docx 是否已被索引覆盖。"""
    covered = _codes_in_index(paths.output_dataset / index_name)
    groups = []
    for twd in sorted(paths.input_archives.iterdir()) if paths.input_archives.exists() else []:
        if not twd.is_dir():
            continue
        items = []
        for docx in sorted(twd.glob("*.docx")):
            if docx.name.startswith("~$"):
                continue
            # 档案编号一般是 docx 文件名开头的 XXXXXX-XXXX
            m = re.match(r"([\d]{6}-[\d\-A-Za-z]+)", docx.stem)
            code = m.group(1) if m else docx.stem
            done = code in covered
            items.append({
                "id": code,
                "name": docx.name,
                "status": "done" if done else "pending",
                "input_size_kb": round(docx.stat().st_size / 1024, 1),
            })
        done_n = sum(1 for i in items if i["status"] == "done")
        groups.append({
            "name": _strip_ordinal(twd.name),
            "total": len(items),
            "done": done_n,
            "pending": len(items) - done_n,
            "items": items,
        })
    return {"step": "input_docx", "groups": groups, "index_covered": len(covered)}


def _items_step05(paths) -> dict:
    in_dir = paths.input_worklogs
    out_dir = paths.output_worklogs
    items = []
    for xlsx in sorted(in_dir.rglob("*.xlsx")) if in_dir.exists() else []:
        if xlsx.name.startswith("~$"):
            continue
        m = re.search(r"(20\d{6})", xlsx.stem)
        date_key = m.group(1) if m else xlsx.stem
        pdf = out_dir / f"{date_key}.pdf"
        items.append({
            "id": date_key,
            "name": xlsx.name,
            "status": "done" if pdf.exists() else "pending",
            "output": pdf.name if pdf.exists() else None,
            "output_size_kb": round(pdf.stat().st_size / 1024, 1) if pdf.exists() else 0,
        })
    done_n = sum(1 for i in items if i["status"] == "done")
    return {
        "step": "step05_convert_worklogs",
        "groups": [{"name": "工作日志", "total": len(items), "done": done_n,
                    "pending": len(items) - done_n, "items": items}],
    }


def _items_step06(paths) -> dict:
    layers = [
        ("county", "县界", paths.output_boundaries / "county.geojson"),
        ("townships", "乡镇界", paths.output_boundaries / "townships.geojson"),
        ("villages", "村界", paths.output_boundaries / "villages.geojson"),
    ]
    items = []
    for key, label, path in layers:
        n = _count_geojson_features(path)
        items.append({
            "id": key,
            "name": label,
            "status": "done" if path.exists() else "pending",
            "feature_count": n,
            "output": path.name if path.exists() else None,
            "output_size_kb": round(path.stat().st_size / 1024, 1) if path.exists() else 0,
            "output_mtime": _mtime_str(path),
        })
    done_n = sum(1 for i in items if i["status"] == "done")
    return {
        "step": "step06_prepare_boundaries",
        "groups": [{"name": "行政边界层", "total": len(items), "done": done_n,
                    "pending": len(items) - done_n, "items": items}],
    }


# ── 任务执行 ────────────────────────────────────────────────
def _run_script_sync(script_path: str, task_id: str, extra_env: Optional[dict] = None) -> None:
    """阻塞执行脚本并把最后 300 行输出挂到 _tasks[task_id]['log'],
    供前端 polling /admin/task/<id> 实时看进度。由线程池调用。"""
    import subprocess
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    if extra_env:
        env.update(extra_env)

    _tasks[task_id]["status"] = "running"
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
        for line in proc.stdout:
            lines.append(line.rstrip("\n"))
            _tasks[task_id]["log"] = lines[-300:]
        proc.wait()
        _tasks[task_id]["returncode"] = proc.returncode
        _tasks[task_id]["status"] = "done" if proc.returncode == 0 else "error"
        _tasks[task_id]["finished"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        _tasks[task_id]["status"] = "error"
        _tasks[task_id]["log"] = _tasks[task_id].get("log", []) + [f"Exception: {e}"]


@router.post("/run/{script_name}")
async def run_script(script_name: str):
    """触发指定脚本异步后台执行。支持短别名(process_docs 等)与完整名(step01_convert_docs)。
    同名脚本已在跑时返回 409。"""
    real = _resolve_script(script_name)
    for tid, t in _tasks.items():
        if t["script"] == real and t["status"] == "running":
            raise HTTPException(409, f"{real} 正在运行中 (task={tid})")

    task_id = str(uuid.uuid4())[:8]
    _tasks[task_id] = {
        "status": "starting",
        "script": real,
        "started": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "log": [],
        "returncode": None,
    }
    script_path = str(SCRIPTS[real])
    asyncio.get_event_loop().run_in_executor(
        None, _run_script_sync, script_path, task_id, None
    )
    return {"task_id": task_id, "script": real}


@router.get("/task/{task_id}")
async def get_task(task_id: str):
    t = _tasks.get(task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    return t


@router.get("/tasks")
async def list_tasks(limit: int = 30):
    """最近的任务历史(默认 30 条,含日志摘要供任务历史表使用)。"""
    items = []
    for tid, t in _tasks.items():
        items.append({
            "task_id": tid,
            "script": t["script"],
            "status": t["status"],
            "started": t["started"],
            "finished": t.get("finished"),
            "returncode": t.get("returncode"),
            "last_log": t.get("log", [])[-1] if t.get("log") else "",
        })
    items.sort(key=lambda x: x["started"], reverse=True)
    return items[:limit]


@router.post("/upload-single")
async def upload_single(
    file: UploadFile = File(...),
    township: str = Form(...),
):
    """单文件上传: data/input/01_archives/<township>/<filename>.docx。"""
    if not file.filename or not file.filename.endswith(".docx"):
        raise HTTPException(400, "仅支持 .docx 文件")

    target_dir = get_paths().input_archives / township
    if not target_dir.exists():
        raise HTTPException(400, f"乡镇文件夹不存在: {township}")

    dest = target_dir / file.filename
    content = await file.read()
    dest.write_bytes(content)

    return {
        "message": f"已保存到 {dest}",
        "township": township,
        "filename": file.filename,
        "size_kb": round(len(content) / 1024, 1),
    }


@router.post("/process-single")
async def process_single(
    file: UploadFile = File(...),
    township: str = Form(...),
):
    """上传 docx 并立即触发 step01。step01 自身会跳过已存在的有效 md,
    所以对已处理的档案再次触发是安全的。"""
    if not file.filename or not file.filename.endswith(".docx"):
        raise HTTPException(400, "仅支持 .docx 文件")

    target_dir = get_paths().input_archives / township
    if not target_dir.exists():
        raise HTTPException(400, f"乡镇文件夹不存在: {township}")

    dest = target_dir / file.filename
    content = await file.read()
    dest.write_bytes(content)

    task_id = str(uuid.uuid4())[:8]
    _tasks[task_id] = {
        "status": "starting",
        "script": "step01_convert_docs",
        "started": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "log": [f"已上传: {file.filename} → {township}"],
        "returncode": None,
        "single_file": file.filename,
    }
    script_path = str(SCRIPTS["step01_convert_docs"])
    asyncio.get_event_loop().run_in_executor(
        None, _run_script_sync, script_path, task_id, None
    )
    return {
        "task_id": task_id,
        "message": f"已上传 {file.filename} 并开始提取",
        "township": township,
    }


# ── 文物 CRUD（走 DB + 乐观锁 + 审计）──────────────────────
# 这些接口只在 DB 模式可用。前端（或脚本）传入 expected_version 做并发保护，
# 冲突返回 409，调用方需重新拉一遍最新记录再提交。

def _require_db() -> None:
    if not getattr(store, "_use_db", False):
        raise HTTPException(503, "DB 未启用；请先运行 step07_build_db.py 并重启服务")


def _normalize_relic_payload(raw: dict) -> dict:
    """把可能带中文的提交体（category_main/heritage_level 等）标准化到 DB 字段。
    已经传编码的（category=0300）就原样保留。"""
    p = dict(raw or {})
    if "category_main" in p and "category" not in p:
        p["category"] = normalize_category(p.pop("category_main"))
    elif "category" in p:
        p["category"] = normalize_category(p["category"])
    if "heritage_level" in p and "rank" not in p:
        p["rank"] = normalize_rank(p.pop("heritage_level"))
    elif "rank" in p:
        p["rank"] = normalize_rank(p["rank"])
    if "survey_type" in p and "search_type" not in p:
        p["search_type"] = normalize_search_type(p.pop("survey_type"))

    # 允许 center_lng / center_lat 命名（和 legacy JSON 一致）
    if "center_lng" in p and "lng" not in p:
        p["lng"] = p.pop("center_lng")
    if "center_lat" in p and "lat" not in p:
        p["lat"] = p.pop("center_lat")
    if "center_alt" in p and "alt" not in p:
        p["alt"] = p.pop("center_alt")
    # archive_code 兼容
    if "archive_code" in p and "code" not in p:
        p["code"] = p.pop("archive_code")
    return p


@router.post("/relics")
async def create_relic(
    payload: dict = Body(...),
    x_actor: Optional[str] = Header(None, alias="X-Actor"),
):
    """创建一条文物。payload 至少包含 code、name、lng、lat。"""
    _require_db()
    try:
        after = store.create_relic(_normalize_relic_payload(payload), actor=x_actor or "")
    except ValueError as e:
        msg = str(e)
        code = 409 if "已存在" in msg else 400
        raise HTTPException(code, msg)
    return {"ok": True, "relic": after}


@router.put("/relics/{code}")
async def update_relic(
    code: str,
    payload: dict = Body(...),
    x_actor: Optional[str] = Header(None, alias="X-Actor"),
):
    """更新文物。payload 必须带 expected_version 做乐观锁。
    version 不匹配返回 409，调用方应刷新后重试。"""
    _require_db()
    ev = payload.pop("expected_version", None)
    if ev is None:
        raise HTTPException(400, "缺少 expected_version（乐观锁）")
    try:
        after = store.update_relic(
            code, _normalize_relic_payload(payload),
            expected_version=int(ev), actor=x_actor or "",
        )
    except ValueError as e:
        msg = str(e)
        if msg == "VERSION_CONFLICT":
            raise HTTPException(409, "版本冲突：数据已被他人修改，请重新加载")
        if "不存在" in msg:
            raise HTTPException(404, msg)
        raise HTTPException(400, msg)
    return {"ok": True, "relic": after}


@router.delete("/relics/{code}")
async def delete_relic(
    code: str,
    x_actor: Optional[str] = Header(None, alias="X-Actor"),
):
    """软删除（status=-1），可以通过 /relics/{code} 更新 status=1 恢复。"""
    _require_db()
    try:
        store.delete_relic(code, actor=x_actor or "")
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"ok": True}


@router.get("/audit")
async def list_audit(
    code: Optional[str] = None,
    limit: int = 100,
    action: Optional[str] = Query(None, description="多值逗号分隔：create,update,delete,rollback"),
    actor: Optional[str] = None,
    field: Optional[str] = Query(None, description="字段名 LIKE 过滤，如 'lng' / 'name'"),
    start_ts: Optional[int] = None,
    end_ts: Optional[int] = None,
):
    """读审计日志（最近的在前），支持多条件筛选。"""
    _require_db()
    actions = [a.strip() for a in (action or "").split(",") if a.strip()] or None
    return {
        "rows": store.list_audit(
            code=code, limit=max(1, min(limit, 500)),
            actions=actions,
            actor=(actor or "").strip() or None,
            field=(field or "").strip() or None,
            start_ts=start_ts, end_ts=end_ts,
        )
    }


@router.post("/audit/{audit_id}/rollback")
async def rollback_audit(
    audit_id: int,
    x_actor: Optional[str] = Header(None, alias="X-Actor"),
):
    """按某条审计记录回滚对应文物到 before_json 状态。"""
    _require_db()
    try:
        return store.rollback_audit(audit_id, actor=x_actor or "")
    except ValueError as e:
        msg = str(e)
        if msg == "VERSION_CONFLICT":
            raise HTTPException(409, "版本冲突：文物已被他人修改，请刷新后重试")
        if "不存在" in msg or "已彻底删除" in msg:
            raise HTTPException(404, msg)
        raise HTTPException(400, msg)


@router.get("/stats-overview")
async def stats_overview():
    """后台 Dashboard 聚合指标。一次 SQL 出所有卡片和图表数据。
    DB 未启用时走 legacy 内存聚合，仅返回最基础字段。"""
    return store.admin_stats_overview()


@router.get("/codes")
async def codes_dict():
    """字典：category / rank / search_type → 中文标签。
    前端列表页、编辑页、筛选器共用，避免两边写死。"""
    return {
        "categories": [{"code": c, "label": CATEGORY_CODES[c]} for c in CATEGORY_CODES],
        "ranks": [{"code": c, "label": RANK_CODES[c]} for c in RANK_CODES],
        "search_types": [{"code": c, "label": SEARCH_TYPE_CODES[c]} for c in SEARCH_TYPE_CODES],
    }


@router.get("/relics-townships")
async def relics_townships():
    """DB 里已入库文物用到的乡镇下拉。"""
    _require_db()
    return {"townships": store.admin_list_townships()}


def _parse_bbox(bbox: Optional[str]) -> Optional[tuple]:
    """'minLng,minLat,maxLng,maxLat' → (mnl, mnt, mxl, mxt)；格式非法返回 None。"""
    if not bbox:
        return None
    parts = [p.strip() for p in bbox.split(",") if p.strip()]
    if len(parts) != 4:
        return None
    try:
        mnl, mnt, mxl, mxt = [float(p) for p in parts]
        return (mnl, mnt, mxl, mxt)
    except ValueError:
        return None


@router.get("/relics")
async def list_relics(
    page: int = 1,
    size: int = 20,
    search: Optional[str] = None,
    category: Optional[str] = None,
    rank: Optional[str] = None,
    township: Optional[str] = None,
    search_type: Optional[str] = None,
    status: Optional[int] = None,
    bbox: Optional[str] = Query(None, description="minLng,minLat,maxLng,maxLat"),
    order_by: str = "updated_at_desc",
):
    """后台分页列表。`category` / `rank` 支持逗号分隔多选。"""
    _require_db()
    categories = [c for c in (category or "").split(",") if c] or None
    ranks = [c for c in (rank or "").split(",") if c] or None
    return store.admin_list_relics(
        page=page, size=size, search=(search or "").strip() or None,
        categories=categories, ranks=ranks,
        township=(township or "").strip() or None,
        search_type=(search_type or "").strip() or None,
        status=status,
        bbox=_parse_bbox(bbox),
        order_by=order_by,
    )


@router.get("/relics/{code}/neighbors")
async def relic_neighbors(
    code: str,
    radius: float = Query(2000.0, ge=50, le=50000, description="米"),
    limit: int = Query(20, ge=1, le=100),
):
    """返回 `code` 附近 `radius` 米内的其它文物（按距离升序）。"""
    _require_db()
    return {
        "code": code, "radius": radius,
        "items": store.admin_neighbors(code, radius_m=radius, limit=limit),
    }


@router.get("/relics/{code}")
async def get_relic_full(code: str):
    """取一条文物的全字段（给编辑页初始化用），包含 _version 供乐观锁。"""
    _require_db()
    r = store.get_relic_full(code) if hasattr(store, "get_relic_full") else store.get_relic(code)
    if not r:
        raise HTTPException(404, f"未找到文物: {code}")
    return r


@router.post("/relics/bulk-update")
async def bulk_update_relics(
    payload: dict = Body(...),
    x_actor: Optional[str] = Header(None, alias="X-Actor"),
):
    """批量同字段更新。payload: `{codes: [..], fields: {...}}`。

    - `fields` 只保留可写字段；不接受 `expected_version`（每条各自拿当前 version）。
    - 乐观锁冲突 / 不存在 / 失败，各自记录在返回里，不影响其他条目。
    """
    _require_db()
    codes = payload.get("codes") or []
    fields = payload.get("fields") or {}
    if not isinstance(codes, list) or not codes:
        raise HTTPException(400, "codes 不能为空")
    if not isinstance(fields, dict) or not fields:
        raise HTTPException(400, "fields 不能为空")
    patch = _normalize_relic_payload(fields)
    # code 本身不允许改；status 单独走 bulk-status 语义更清晰，这里一并允许
    patch.pop("code", None)
    try:
        return store.admin_bulk_update(codes, patch, actor=x_actor or "")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/relics/bulk-status")
async def bulk_set_status(
    payload: dict = Body(...),
    x_actor: Optional[str] = Header(None, alias="X-Actor"),
):
    """批量改状态：`{codes:[...], status: 1|0|-1}`。

    status=-1 走软删除接口（写 audit action=delete），1 / 0 走 bulk_update（action=update）。
    """
    _require_db()
    codes = payload.get("codes") or []
    status = payload.get("status")
    if not isinstance(codes, list) or not codes:
        raise HTTPException(400, "codes 不能为空")
    if status not in (1, 0, -1):
        raise HTTPException(400, "status 只能是 1 / 0 / -1")
    if status == -1:
        return store.admin_bulk_delete(codes, actor=x_actor or "")
    return store.admin_bulk_update(codes, {"status": int(status)}, actor=x_actor or "")


@router.get("/relics-export")
async def export_relics(
    search: Optional[str] = None,
    category: Optional[str] = None,
    rank: Optional[str] = None,
    township: Optional[str] = None,
    search_type: Optional[str] = None,
    status: Optional[int] = None,
    codes: Optional[str] = Query(None, description="逗号分隔的 code 列表；给出时忽略其他筛选"),
    bbox: Optional[str] = Query(None, description="minLng,minLat,maxLng,maxLat"),
    order_by: str = "code_asc",
):
    """按当前筛选条件或显式 code 列表导出 CSV（UTF-8 BOM，Excel 直接可打开）。

    返回列：code,name,category,category_label,rank,rank_label,search_type,search_type_label,
          era,era_stats,lng,lat,alt,township,village,address,has_3d,has_pdf,has_photo,
          has_boundary,photo_count,drawing_count,status,version,updated_at,brief
    """
    _require_db()
    cat_list = [c for c in (category or "").split(",") if c] or None
    rank_list = [c for c in (rank or "").split(",") if c] or None
    code_list = [c.strip() for c in (codes or "").split(",") if c.strip()] or None

    fieldnames = [
        "code", "name",
        "category", "category_label",
        "rank", "rank_label",
        "search_type", "search_type_label",
        "era", "era_stats",
        "lng", "lat", "alt",
        "township", "village", "address",
        "has_3d", "has_pdf", "has_photo", "has_boundary",
        "photo_count", "drawing_count",
        "status", "version", "updated_at",
        "brief",
    ]

    def _gen():
        import io
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
        # Excel 友好的 UTF-8 BOM
        yield "\ufeff"
        writer.writeheader()
        yield buf.getvalue()
        buf.seek(0); buf.truncate(0)
        rows = store.admin_export_relics(
            search=(search or "").strip() or None,
            categories=cat_list, ranks=rank_list,
            township=(township or "").strip() or None,
            search_type=(search_type or "").strip() or None,
            status=status,
            codes=code_list,
            bbox=_parse_bbox(bbox),
            order_by=order_by,
        )
        for r in rows:
            row = dict(r)
            row["category_label"] = CATEGORY_CODES.get(str(row.get("category") or ""), "")
            row["rank_label"] = RANK_CODES.get(str(row.get("rank") or ""), "")
            row["search_type_label"] = SEARCH_TYPE_CODES.get(str(row.get("search_type") or ""), "")
            # bool 导出成 0/1，excel 友好
            for k in ("has_3d", "has_pdf", "has_photo", "has_boundary"):
                row[k] = 1 if row.get(k) else 0
            writer.writerow(row)
            yield buf.getvalue()
            buf.seek(0); buf.truncate(0)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"relics-{ts}.csv"
    return StreamingResponse(
        _gen(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/relics/import")
async def import_relics(
    file: UploadFile = File(...),
    mode: str = Form("upsert"),          # upsert / create_only
    x_actor: Optional[str] = Header(None, alias="X-Actor"),
):
    """批量导入文物：接受 CSV / JSON 数组，按 code 匹配：
    - mode=upsert：已有的走 update_relic（带版本号从 DB 读），新增的走 create_relic
    - mode=create_only：已有则跳过，仅新增

    返回每行的处理结果，方便前端展示。大文件时建议分批，本接口没有事务整体包装。
    """
    _require_db()
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "空文件")

    items: list[dict] = []
    name = (file.filename or "").lower()
    if name.endswith(".json"):
        try:
            data = json.loads(raw.decode("utf-8-sig"))
        except json.JSONDecodeError as e:
            raise HTTPException(400, f"JSON 解析失败: {e}")
        if not isinstance(data, list):
            raise HTTPException(400, "JSON 顶层需是数组")
        items = data
    elif name.endswith(".csv"):
        import io
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        items = list(reader)
    else:
        raise HTTPException(400, "仅支持 .csv / .json")

    results = {"created": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []}
    for idx, raw_row in enumerate(items, start=1):
        p = _normalize_relic_payload(raw_row)
        code = (p.get("code") or "").strip()
        if not code:
            results["skipped"] += 1
            continue
        try:
            existing = store.get_relic(code)
            if existing:
                if mode == "create_only":
                    results["skipped"] += 1
                    continue
                ev = existing.get("_version")
                if ev is None:
                    # legacy dict 里没 version，直接查 DB 拿最新
                    row = store._thread_conn().execute(
                        "SELECT version FROM relics WHERE code = ?", (code,)
                    ).fetchone()
                    ev = int(row["version"]) if row else 1
                store.update_relic(code, p, expected_version=int(ev), actor=x_actor or "import")
                results["updated"] += 1
            else:
                store.create_relic(p, actor=x_actor or "import")
                results["created"] += 1
        except Exception as e:
            results["failed"] += 1
            results["errors"].append({"line": idx, "code": code, "error": str(e)})
            if len(results["errors"]) > 50:
                break

    return results
