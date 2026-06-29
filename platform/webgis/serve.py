"""WebGIS 启动入口。

由 `start-backend.bat` 调用:读取 config.yaml 拿 host/port,然后起 uvicorn,
避免在 .bat 脚本里解析 YAML。
"""
from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

from _common import load_config  # noqa: E402


def _open_browser_delayed(url: str, delay: float = 2.0) -> None:
    """延迟打开浏览器,等 uvicorn 绑定端口成功后再访问。"""
    def _worker() -> None:
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            pass
    t = threading.Thread(target=_worker, daemon=True)
    t.start()


def main() -> int:
    try:
        cfg = load_config()
    except FileNotFoundError as e:
        print(f"[错误] {e}", file=sys.stderr)
        return 2

    srv = cfg.get("server", {}) or {}
    host = str(srv.get("host", "127.0.0.1"))
    port = int(srv.get("port", 8000))

    proj = cfg.get("project", {}) or {}
    name = proj.get("full_name") or proj.get("name") or "Relics Platform"

    browser_url = f"http://127.0.0.1:{port}" if host == "0.0.0.0" \
        else f"http://{host}:{port}"
    dev_app = os.environ.get("RELICS_DEV_APP_URL", "").strip().rstrip("/")
    dev_admin = os.environ.get("RELICS_DEV_ADMIN_URL", "").strip().rstrip("/")

    print("=" * 56)
    print(f"  {name}" + ("(开发模式)" if dev_app else ""))
    print("=" * 56)
    if dev_app:
        print(f"  React WebGIS(主应用): {dev_app}/")
        if dev_admin:
            print(f"  Vue 后台管理:         {dev_admin}/")
        print(f"  后端 API:             {browser_url}")
        print("=" * 56)
        print("  关闭启动窗口或 Ctrl+C 停止全部服务")
    else:
        print(f"  平台地址: {browser_url}")
        print("=" * 56)
        print("  关闭本窗口即可停止服务")
    print()

    # 仅在存在前端构建产物(React dist)时才自动打开浏览器:开发模式下没有
    # dist,根路径 / 会回退到旧版 templates/index.html,自动弹出会让人误以为
    # 那是当前版本。可用 config.yaml 的 server.open_browser 覆盖(true/false)。
    react_dist = HERE.parent / "webgis-react" / "dist" / "index.html"
    open_browser = srv.get("open_browser", "auto")
    if isinstance(open_browser, str) and open_browser.lower() in ("false", "no", "off"):
        open_browser = False
    elif isinstance(open_browser, str) and open_browser.lower() in ("true", "yes", "on"):
        open_browser = True
    else:  # auto:有构建产物才打开,避免弹出旧版兜底页
        open_browser = react_dist.exists()

    if not dev_app and open_browser:
        _open_browser_delayed(browser_url, delay=2.0)
    elif not dev_app:
        print("[INFO] 未检测到前端构建产物(dist),不自动打开浏览器。")
        print("       开发模式请运行 start-frontend.bat(5173=Vue 后台 / 5174=React WebGIS)。")

    import uvicorn
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        app_dir=str(HERE),
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
