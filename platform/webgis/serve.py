"""WebGIS 后端启动入口。

由 start.py(经 start-all.bat / start-all.sh)调用,也可单独运行起纯后端:
读取 config.yaml 拿 host/port,然后起 uvicorn,避免在启动脚本里解析 YAML。
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


_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def insecure_bind_reason(host: str, enable_auth: bool, allow_insecure: bool) -> str | None:
    """生产闸门:绑定非回环地址 + 未开鉴权 + 未显式放行 → 返回拒绝理由,否则 None。

    防止"把 server.host 改成 0.0.0.0 却忘了开 enable_auth",导致局域网任意主机
    可无鉴权调用所有写接口(CRUD/导入/边界清理/瓦片任务)。
    """
    if host in _LOOPBACK_HOSTS or enable_auth or allow_insecure:
        return None
    return (
        f"server.host={host} 绑定到非回环地址,但 server.enable_auth=false —— "
        "局域网任意主机可无鉴权调用所有写接口。请二选一:"
        "1) 开启 server.enable_auth=true 并配置 server.users;"
        "2) 仅本机调试且确实要裸跑时,显式设置 server.allow_insecure_demo=true。"
    )


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

    # 安全闸门:非回环绑定 + 未开鉴权 → 拒绝启动(可用 allow_insecure_demo 显式放行)。
    reason = insecure_bind_reason(
        host,
        bool(srv.get("enable_auth", False)),
        bool(srv.get("allow_insecure_demo", False)),
    )
    if reason:
        print("[安全] 拒绝启动:", reason, file=sys.stderr)
        return 2
    if not srv.get("enable_auth", False):
        print("[安全] 提示:server.enable_auth=false,登录将直接签发 session(仅限本机调试)。",
              file=sys.stderr)

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
        print("       开发模式请运行 start-all.bat / start-all.sh(同时起后端 + 5173 Vue 后台 + 5174 React WebGIS)。")

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
