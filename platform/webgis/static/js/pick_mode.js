// 与后台管理系统（/admin-ui/）打通的 URL 参数 & 拾点模式。
//
// 约定：
//   /?relic=<code>        打开主图后自动 flyTo + showInfo 到该文物
//   /?pick=1              进入拾点模式，单击地图任意处后把经纬度 postMessage 回 opener
//   /?pick=1&code=<code>  带 code 时表示"给这条文物选坐标"，回传消息里带上
//
// postMessage 协议（发送给 window.opener，targetOrigin=当前 origin）：
//   { type: 'relic-pick', lng: number, lat: number, alt: number|null, code: string|null }
//   { type: 'relic-pick-cancel' }
//
// 由 app.js 在 init() 完成后调用 window.PickMode.handleUrlParams()。
(function () {
    'use strict';

    const STATE = {
        enabled: false,
        code: null,           // 当前被编辑的文物 code（仅做回显，可为空）
        handler: null,        // Cesium ScreenSpaceEventHandler
        banner: null,         // 顶部横幅 DOM
        prevCursor: null,     // 进入时的 canvas cursor，退出时还原
    };

    function _canvas() {
        return (window.viewer && viewer.scene && viewer.scene.canvas) || null;
    }

    // 顶部横幅，直观告诉管理员"你在点选坐标"
    function _mountBanner() {
        if (STATE.banner) return;
        const b = document.createElement('div');
        b.id = 'pickModeBanner';
        b.style.cssText = [
            'position:fixed', 'top:0', 'left:0', 'right:0', 'z-index:99999',
            'padding:10px 16px', 'background:linear-gradient(90deg,#b45309,#d97706)',
            'color:#fff', 'font-size:14px', 'font-weight:600',
            'display:flex', 'align-items:center', 'justify-content:center', 'gap:12px',
            'box-shadow:0 2px 8px rgba(0,0,0,.4)',
            'font-family:system-ui,-apple-system,Segoe UI,sans-serif',
        ].join(';');
        const label = STATE.code
            ? `拾取坐标模式 · 当前文物 ${STATE.code}`
            : '拾取坐标模式 · 新建文物';
        b.innerHTML = `
            <span>📍 ${label}</span>
            <span style="opacity:.85;font-weight:400">单击地图任意位置拾取经纬度；ESC 或点右侧按钮取消</span>
            <button id="pickCancelBtn" style="margin-left:8px;padding:4px 12px;background:rgba(0,0,0,.3);color:#fff;border:1px solid rgba(255,255,255,.4);border-radius:4px;cursor:pointer;font-size:12px">取消</button>
        `;
        document.body.appendChild(b);
        b.querySelector('#pickCancelBtn').addEventListener('click', cancel);
        STATE.banner = b;
    }

    function _unmountBanner() {
        if (STATE.banner) {
            STATE.banner.remove();
            STATE.banner = null;
        }
    }

    // 解析屏幕坐标 → 经纬度/高度。命中地形优先，否则打到地球椭球。
    function _screenToLngLat(click) {
        const viewer = window.viewer;
        if (!viewer) return null;
        // 优先用 pickPosition（命中模型/地形）
        let carto = null;
        if (viewer.scene.pickPositionSupported) {
            const cartesian = viewer.scene.pickPosition(click.position);
            if (Cesium.defined(cartesian)) {
                carto = Cesium.Cartographic.fromCartesian(cartesian);
            }
        }
        // 否则用射线与椭球的交点
        if (!carto) {
            const ray = viewer.camera.getPickRay(click.position);
            if (!ray) return null;
            const cartesian = viewer.scene.globe.pick(ray, viewer.scene);
            if (!Cesium.defined(cartesian)) return null;
            carto = Cesium.Cartographic.fromCartesian(cartesian);
        }
        return {
            lng: +Cesium.Math.toDegrees(carto.longitude).toFixed(6),
            lat: +Cesium.Math.toDegrees(carto.latitude).toFixed(6),
            alt: Number.isFinite(carto.height) ? +carto.height.toFixed(1) : null,
        };
    }

    function _onPickClick(click) {
        const coord = _screenToLngLat(click);
        if (!coord) {
            if (typeof toast === 'function') toast('未能拾取到坐标，请再试一次');
            return;
        }
        _postBack({
            type: 'relic-pick',
            lng: coord.lng,
            lat: coord.lat,
            alt: coord.alt,
            code: STATE.code,
        });
        if (typeof toast === 'function') {
            toast(`已拾取：${coord.lng.toFixed(5)}, ${coord.lat.toFixed(5)}`);
        }
        // 默认回传后自动退出 + 关窗，让管理员回到编辑表单继续操作
        disable();
        // 给 Element Plus 发消息留 200ms，再关自己
        setTimeout(() => {
            if (window.opener && !window.opener.closed) {
                try { window.close(); } catch (_) {}
            }
        }, 250);
    }

    // 推断 opener 的 origin：
    //   - 生产期后台和主图同源（都在 FastAPI 下），用 window.location.origin 最安全
    //   - 开发期后台在 :5173、主图在 :8000 跨源，走 document.referrer 拿 opener origin
    //   - 都拿不到时退到 '*'（消息体仅含坐标，无敏感信息）
    function _openerOrigin() {
        try {
            if (document.referrer) {
                const o = new URL(document.referrer).origin;
                if (o && o !== 'null') return o;
            }
        } catch (_) {}
        return null;
    }

    function _postBack(msg) {
        try {
            const target = window.opener || (window.parent !== window ? window.parent : null);
            if (!target) return;
            const origin = _openerOrigin();
            // 优先同源；若跨源（开发模式）则按 referrer 推断，最后兜底 '*'
            target.postMessage(msg, origin || '*');
        } catch (e) {
            console.warn('[pick_mode] postBack 失败', e);
        }
    }

    function enable(opts) {
        if (STATE.enabled) return;
        const viewer = window.viewer;
        if (!viewer) {
            console.warn('[pick_mode] viewer 未就绪');
            return;
        }
        STATE.enabled = true;
        STATE.code = (opts && opts.code) || null;

        _mountBanner();

        const canvas = _canvas();
        if (canvas) {
            STATE.prevCursor = canvas.style.cursor;
            canvas.style.cursor = 'crosshair';
        }

        STATE.handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
        STATE.handler.setInputAction(_onPickClick, Cesium.ScreenSpaceEventType.LEFT_CLICK);

        document.addEventListener('keydown', _onKeyDown, true);
    }

    function disable() {
        if (!STATE.enabled) return;
        STATE.enabled = false;
        if (STATE.handler) {
            STATE.handler.destroy();
            STATE.handler = null;
        }
        const canvas = _canvas();
        if (canvas) canvas.style.cursor = STATE.prevCursor || '';
        _unmountBanner();
        document.removeEventListener('keydown', _onKeyDown, true);
    }

    function cancel() {
        _postBack({ type: 'relic-pick-cancel' });
        disable();
        setTimeout(() => {
            if (window.opener && !window.opener.closed) {
                try { window.close(); } catch (_) {}
            }
        }, 150);
    }

    function _onKeyDown(e) {
        if (e.key === 'Escape') {
            e.stopPropagation();
            e.preventDefault();
            cancel();
        }
    }

    // ── URL 参数入口 ────────────────────────────────────
    // 处理 ?relic / ?pick。由 app.js 在 init() 结束后调用。
    function handleUrlParams() {
        const params = new URLSearchParams(window.location.search);

        const pick = params.get('pick');
        if (pick === '1' || pick === 'true') {
            const code = params.get('code');
            // viewer 可能还在加载地形/影像，enable() 只需 viewer 对象存在即可
            enable({ code });
            return;
        }

        const relic = params.get('relic');
        if (relic) {
            _autoFocusRelic(relic);
        }
    }

    // 打开主图时若带 ?relic=code，自动飞到该文物并弹信息面板
    function _autoFocusRelic(code) {
        const tryFly = () => {
            if (typeof window.flyTo === 'function'
                && Array.isArray(window.allRelics) && window.allRelics.length) {
                if (window.allRelics.some(r => r.archive_code === code)) {
                    window.flyTo(code);
                    return true;
                }
            }
            // 即便 allRelics 里没有（筛选模式下可能被过滤），也尝试直接调 showInfoByCode
            if (typeof window.showInfoByCode === 'function') {
                window.showInfoByCode(code);
                return true;
            }
            return false;
        };
        // 等 allRelics 就绪，轮询最多 10s
        let tries = 0;
        const t = setInterval(() => {
            tries += 1;
            if (tryFly() || tries > 50) clearInterval(t);
        }, 200);
    }

    window.PickMode = { enable, disable, cancel, handleUrlParams };
})();
