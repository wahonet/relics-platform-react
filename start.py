#!/usr/bin/env python3
"""一键启动整个文物档案平台(后端 + 两个前端 dev server)。

跨平台:Windows 与麒麟等 Linux 桌面行为一致。
- Windows:双击 start-all.bat
- Linux/麒麟:./start-all.sh

设计要点:
- 三个服务的日志在同一控制台内带前缀/颜色输出,谁说话一目了然。
- Ctrl+C 一次性干净退出全部子进程(含 npm/node 衍生进程)。
- 首次运行自动 bootstrap:复制 config.yaml、装后端 Python 依赖、
  装前端 npm 依赖、创建 data/ 目录骨架。
- 端口:后端读 config.yaml(默认 8000),前端用各自 vite.config 固定值
  (Vue 后台 5173 / React WebGIS 5174)。

注意:本脚本由包装脚本(start-all.bat / start-all.sh)选好 Python 解释器后
调用,内部统一用 sys.executable 跑后端,避免在两套平台重复实现解释器探测。
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEBGIS_DIR = ROOT / "platform" / "webgis"
VUE_DIR = ROOT / "platform" / "admin-vue"
REACT_DIR = ROOT / "platform" / "webgis-react"

# 后端启动需要绕过系统代理的域名(地图/瓦片源 + 本地回环)。
_NO_PROXY = (
    "geo.datav.aliyun.com,overpass-api.de,overpass.kumi.systems,"
    "overpass.openstreetmap.fr,overpass.osm.ch,tile.openstreetmap.org,"
    "server.arcgisonline.com,wprd01.is.autonavi.com,wprd02.is.autonavi.com,"
    "wprd03.is.autonavi.com,wprd04.is.autonavi.com,webst01.is.autonavi.com,"
    "webst02.is.autonavi.com,webst03.is.autonavi.com,webst04.is.autonavi.com,"
    "127.0.0.1,localhost"
)

# 启动后自动打开、且后端 / 会跳转到的"主应用"地址(React WebGIS dev server,
# 端口见 platform/webgis-react/vite.config.ts)。想改成打开 Vue 后台(5173),
# 改这里即可;也可用环境变量 RELICS_OPEN_URL 覆盖。
OPEN_URL = os.environ.get("RELICS_OPEN_URL", "http://127.0.0.1:5174/")
# Vue 后台 dev server 地址(端口见 platform/admin-vue/vite.config.ts)。
ADMIN_DEV_URL = "http://127.0.0.1:5173/"

_TAG_COLOR = {"backend": "\033[36m", "admin": "\033[35m", "webgis": "\033[32m"}
RESET = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"
YELLOW = "\033[33m"
RED = "\033[31m"

_USE_COLOR = sys.stdout.isatty()


def _c(code: str) -> str:
    return code if _USE_COLOR else ""


def _enable_vt() -> None:
    """Windows 上启用 ANSI 转义(VT)处理,让带颜色的日志正常显示。"""
    if os.name != "nt" or not _USE_COLOR:
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        # STD_OUTPUT_HANDLE = -11; mode 7 = PROCESSED(1) | WRAP(2) | VT(4)
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass


def _info(msg: str) -> None:
    print(f"{_c(YELLOW)}{msg}{_c(RESET)}", flush=True)


# ── 首次运行 bootstrap ────────────────────────────────────────
def ensure_config() -> None:
    cfg = ROOT / "config.yaml"
    example = ROOT / "config.example.yaml"
    if cfg.exists():
        return
    if not example.exists():
        sys.exit(f"{_c(RED)}[错误] 缺少 config.yaml 且未找到 config.example.yaml{_c(RESET)}")
    shutil.copy(example, cfg)
    _info("[setup] 已从 config.example.yaml 生成 config.yaml,请按本县/区情况修改后再用。")


def ensure_python_deps(python: str) -> None:
    probe = subprocess.run([python, "-c", "import yaml, fastapi, uvicorn"], capture_output=True)
    if probe.returncode == 0:
        return
    _info("[setup] 安装后端 Python 依赖(首次较慢)...")
    subprocess.run([python, "-m", "pip", "install", "-r", str(WEBGIS_DIR / "requirements.txt")])


def ensure_data_dirs(python: str) -> None:
    code = (
        "import sys; sys.path.insert(0, 'platform/scripts'); "
        "from _common import ensure_data_dirs; ensure_data_dirs()"
    )
    subprocess.run([python, "-c", code], cwd=str(ROOT), capture_output=True)


def ensure_npm_deps(npm: str) -> None:
    for d in (VUE_DIR, REACT_DIR):
        if (d / "node_modules" / "vite").exists():
            continue
        _info(f"[setup] 安装 {d.name} 前端依赖(npm install,首次较慢)...")
        subprocess.run([npm, "install"], cwd=str(d))


def find_npm() -> str | None:
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if npm:
        return npm
    print(
        f"{_c(RED)}[错误] 未找到 npm。前端需要 Node.js LTS (v18+)。{_c(RESET)}\n"
        f"{_c(DIM)}        如只起后端,可直接运行: python platform/webgis/serve.py{_c(RESET)}",
        file=sys.stderr,
    )
    return None


# ── 进程编排 ──────────────────────────────────────────────────
def _spawn(args: list[str], cwd: Path, env: dict | None) -> subprocess.Popen:
    kwargs: dict = dict(
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
    )
    # 各服务独立进程组:Ctrl+C 不会自动扩散到子进程,由本脚本统一收尾。
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(args, **kwargs)


def _pump(proc: subprocess.Popen, tag: str) -> None:
    color = _c(_TAG_COLOR.get(tag, ""))
    prefix = f"{color}{tag:<7}{_c(RESET)} │ "
    assert proc.stdout is not None
    try:
        for line in iter(proc.stdout.readline, ""):
            if line == "":
                break
            if not line.endswith("\n"):
                line += "\n"
            sys.stdout.write(prefix + line)
    finally:
        sys.stdout.flush()


def _kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            # /T 连同 npm→node→vite 衍生子进程一并结束。
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        else:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
    except Exception:
        pass
    try:
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _backend_env() -> dict:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONUNBUFFERED": "1",
            "PYTHONIOENCODING": "utf-8",
            "NO_PROXY": _NO_PROXY,
            "no_proxy": _NO_PROXY,
            # 开发模式:让后端 / 跳到 dev server,并把 dev 地址传给后端做启动横幅
            "RELICS_DEV_APP_URL": OPEN_URL,
            "RELICS_DEV_ADMIN_URL": ADMIN_DEV_URL,
        }
    )
    return env


def _open_when_ready(url: str, timeout: float = 25.0) -> None:
    """轮询 url 直到前端 dev server 就绪(或超时),再打开浏览器。"""
    def _worker() -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=1.5) as r:
                    if r.status < 500:
                        break
            except Exception:
                pass
            time.sleep(0.4)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()


def _wait_any_exit(running: list[tuple[str, subprocess.Popen, threading.Thread]]) -> None:
    while True:
        time.sleep(0.5)
        for tag, proc, _ in running:
            if proc.poll() is not None:
                _info(f"[{tag}] 进程已退出(code={proc.returncode}),停止其余服务。")
                return


def main() -> int:
    _enable_vt()
    print(f"{_c(BOLD)}文物数字档案平台 — 全栈启动(后端 + Vue 后台 + React WebGIS){_c(RESET)}")
    print(f"{_c(DIM)}三个服务在同一控制台输出,Ctrl+C 退出全部。{_c(RESET)}\n")

    python = sys.executable
    npm = find_npm()
    if not npm:
        return 1

    ensure_config()
    ensure_python_deps(python)
    ensure_data_dirs(python)
    ensure_npm_deps(npm)

    services = [
        ("backend", [python, "serve.py"], WEBGIS_DIR, _backend_env()),
        ("admin", [npm, "run", "dev"], VUE_DIR, None),
        ("webgis", [npm, "run", "dev"], REACT_DIR, None),
    ]

    print(f"{_c(DIM)}启动服务...{_c(RESET)}", flush=True)
    running: list[tuple[str, subprocess.Popen, threading.Thread]] = []
    for tag, args, cwd, env in services:
        try:
            proc = _spawn(args, cwd, env)
        except FileNotFoundError as e:
            print(f"{_c(RED)}[错误] 无法启动 {tag}: {e}{_c(RESET)}", file=sys.stderr)
            for _, p, _ in running:
                _kill_tree(p)
            return 1
        t = threading.Thread(target=_pump, args=(proc, tag), daemon=True)
        t.start()
        running.append((tag, proc, t))

    _open_when_ready(OPEN_URL)
    try:
        _wait_any_exit(running)
    except KeyboardInterrupt:
        print(f"\n{_c(YELLOW)}收到 Ctrl+C,正在停止全部服务...{_c(RESET)}")
    finally:
        for _tag, proc, _ in running:
            _kill_tree(proc)
        for _, _, t in running:
            t.join(timeout=1.0)
        print(f"{_c(DIM)}[stop] 已停止全部服务。{_c(RESET)}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
