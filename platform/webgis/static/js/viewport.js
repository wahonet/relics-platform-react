// 视口查询管理：监听 camera.moveEnd，debounce 后拉取 /api/relics/by-bbox，
// 配合 LRU 缓存复用相邻视口的数据，最后喂给 PointRenderer 做 diff 更新。
//
// 依赖全局：window.Cesium, window.viewer, window.PointRenderer, window.Bus
// 输出：window.Viewport（管理对象，提供 start/refresh/setFilters 等方法）
(function () {
    const MAX_CACHE = 32;              // LRU 容量
    const DEBOUNCE_MS = 300;           // camera 停下 300ms 后再拉
    const COORD_DECIMALS = 5;          // URL 参数小数位，保证缓存命中率

    function _debounce(fn, ms) {
        let t;
        return function () {
            const args = arguments;
            clearTimeout(t);
            t = setTimeout(() => fn.apply(null, args), ms);
        };
    }

    class ViewportManager {
        constructor(viewer, renderer) {
            this.viewer = viewer;
            this.renderer = renderer;
            this._filters = {};            // { category, rank, township, search_type }
            this._cache = new Map();       // URL -> data
            this._lastURL = null;
            this._pending = null;

            this._onMoveEnd = _debounce(() => this.refresh(), DEBOUNCE_MS);
        }

        start() {
            this.viewer.camera.moveEnd.addEventListener(this._onMoveEnd);
            // 首次启动：直接拉一次
            this.refresh();
        }

        stop() {
            this.viewer.camera.moveEnd.removeEventListener(this._onMoveEnd);
        }

        // 外部调用：筛选变了强制重刷
        setFilters(filters) {
            this._filters = Object.assign({}, filters || {});
            // 筛选变化时清缓存，避免旧条件的结果被复用
            this._cache.clear();
            this.refresh();
        }

        mergeFilters(delta) {
            this.setFilters(Object.assign({}, this._filters, delta || {}));
        }

        clearFilters() { this.setFilters({}); }

        // 计算当前视口 bbox（WGS84 度）
        _currentBBox() {
            const rect = this.viewer.camera.computeViewRectangle();
            if (!rect) return null;
            const west  = Cesium.Math.toDegrees(rect.west);
            const south = Cesium.Math.toDegrees(rect.south);
            const east  = Cesium.Math.toDegrees(rect.east);
            const north = Cesium.Math.toDegrees(rect.north);
            if (!isFinite(west) || !isFinite(east)) return null;
            return {
                min_lng: west.toFixed(COORD_DECIMALS),
                min_lat: south.toFixed(COORD_DECIMALS),
                max_lng: east.toFixed(COORD_DECIMALS),
                max_lat: north.toFixed(COORD_DECIMALS),
            };
        }

        // 把筛选对象拍平成 URL 参数
        _filtersToParams() {
            const p = {};
            const f = this._filters || {};
            if (f.category)    p.category = Array.isArray(f.category) ? f.category.join(',') : f.category;
            if (f.rank)        p.rank = Array.isArray(f.rank) ? f.rank.join(',') : f.rank;
            if (f.township)    p.township = f.township;
            if (f.search_type) p.search_type = f.search_type;
            return p;
        }

        async refresh() {
            const bbox = this._currentBBox();
            if (!bbox) return;
            const params = Object.assign({}, bbox, this._filtersToParams());
            const qs = new URLSearchParams(params).toString();
            const url = '/api/relics/by-bbox?' + qs;

            // 跟上次同一个 URL 就不重复拉（常见于 moveEnd 触发但视口未变）
            if (url === this._lastURL && this._cache.has(url)) {
                this.renderer.diffUpdate(this._cache.get(url));
                return;
            }
            this._lastURL = url;

            let data = this._cache.get(url);
            if (data) {
                this.renderer.diffUpdate(data);
                // 把命中项移到 LRU 末尾
                this._cache.delete(url);
                this._cache.set(url, data);
                return;
            }

            try {
                const resp = await fetch(url, { credentials: 'same-origin' });
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                const body = await resp.json();
                data = (body && body.data) || [];
                this._cache.set(url, data);
                if (this._cache.size > MAX_CACHE) {
                    // 淘汰最早的一条
                    const first = this._cache.keys().next().value;
                    if (first !== undefined) this._cache.delete(first);
                }
                // 只有最新请求的才喂到渲染器，防止并发请求乱序
                if (this._lastURL === url) {
                    this.renderer.diffUpdate(data);
                    window.Bus && window.Bus.emit('viewport:updated', { total: data.length, truncated: body.truncated });
                }
            } catch (e) {
                console.warn('[Viewport] 查询失败:', e);
            }
        }
    }

    window.ViewportManager = ViewportManager;
})();
