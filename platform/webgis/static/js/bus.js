// 轻量事件总线：用于跨模块解耦通信。
// 不依赖任何第三方库。典型事件名见下方注释。
//
// 约定事件：
//   'filter:changed'     筛选条件变更，payload = { filters: {...} }
//   'viewport:changed'   视口变更，payload = { bbox: {...} }
//   'relic:selected'     文物点被点击，payload = relic 对象
//   'layer:toggled'      图层开关变化，payload = { id, visible }
//   'chat:toggled'       AI 聊天面板开关，payload = { open: bool }
//
// 使用方式（挂 window.Bus，兼容非 ES module 的 <script> 脚本）：
//   Bus.on('filter:changed', (f) => ...);
//   Bus.emit('filter:changed', { filters });
//   Bus.off('filter:changed', fn);
(function () {
    const _listeners = new Map();

    function on(event, fn) {
        if (!_listeners.has(event)) _listeners.set(event, new Set());
        _listeners.get(event).add(fn);
        return () => off(event, fn);
    }

    function off(event, fn) {
        const set = _listeners.get(event);
        if (set) set.delete(fn);
    }

    function emit(event, payload) {
        const set = _listeners.get(event);
        if (!set || set.size === 0) return;
        // 复制一份再遍历，避免订阅方在回调中再次 on/off 引发遍历异常
        [...set].forEach((fn) => {
            try { fn(payload); } catch (e) { console.error('[Bus]', event, e); }
        });
    }

    function once(event, fn) {
        const wrap = (p) => { off(event, wrap); fn(p); };
        on(event, wrap);
    }

    window.Bus = { on, off, emit, once };
})();
