// 应用入口：加载数据、绑定交互、启动。
async function init() {
    try {
        // 1. 先构建地图点渲染器 + 视口查询管理器（即使全量 fetch 失败也能按视口拉）
        window.pointRenderer = new PointRenderer(viewer);
        window.viewport = new ViewportManager(viewer, window.pointRenderer);

        // 2. 全量拉 /api/relics 作为 filter 下拉/图表/AI 聊天的上下文；
        //    地图点位不再由此触发渲染，而是由 viewport 按视口增量拉取。
        const [rResp, sResp] = await Promise.all([
            fetch(API + '/api/relics'), fetch(API + '/api/stats'),
        ]);
        allRelics = await rResp.json();
        const globalStats = await sResp.json();
        allRelics.forEach(r => { activeCats.add(r.category_main); });
        dimColorMaps[activeGroup] = buildColorMap(allRelics, DIMS.find(d=>d.id===activeGroup));
        populateFilters();

        // 3. filter 计算 filtered/列表/图表（不再渲染地图点），
        //    地图点由 viewport 的第一次 moveEnd 触发拉取。
        onFilterChange();
        window.viewport.start();

        loadPolygons();
        loadBoundaries();
        loadSurveyRoutes();
        loadWorklogData();
        document.getElementById('loading').style.display = 'none';

        // 打通后台管理：?relic=code 自动定位；?pick=1 进入拾点模式
        if (window.PickMode && typeof PickMode.handleUrlParams === 'function') {
            PickMode.handleUrlParams();
        }
    } catch (e) {
        console.error(e);
        document.getElementById('loading').innerHTML = '<div style="color:var(--red)">数据加载失败，请检查后端服务</div>';
    }
}

function updateBadges(s) {}

// 单击：显示文物/路线点信息；双击：按乡镇或村筛选。
const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
let _clickTimer = null;
handler.setInputAction(function (click) {
    clearTimeout(_clickTimer);
    _clickTimer = setTimeout(() => {
        const picked = viewer.scene.pick(click.position);
        if (!Cesium.defined(picked)) return;

        // 1. PointPrimitive（新的高性能渲染路径）：picked.id 是 {_type:'relic',code,...}
        if (picked.id && picked.id._type === 'relic' && picked.id.code) {
            showInfoByCode(picked.id.code);
            return;
        }

        // 2. 旧 Entity 路径：路线点 / 行政边界双击筛选 / 遗留 Billboard
        if (picked.id && picked.id.properties) {
            const r = {};
            picked.id.properties.propertyNames.forEach(n => { r[n] = picked.id.properties[n].getValue(); });
            if (r._isRoutePoint) {
                _onRoutePointClick(r);
            } else if (!r._boundaryType && !r._isRouteLine) {
                showInfo(r);
            }
        }
    }, 250);
}, Cesium.ScreenSpaceEventType.LEFT_CLICK);

handler.setInputAction(function (click) {
    clearTimeout(_clickTimer);
    const picked = viewer.scene.pick(click.position);
    if (Cesium.defined(picked) && picked.id && picked.id.properties) {
        try {
            const bt = picked.id.properties._boundaryType;
            if (bt) {
                const type = bt.getValue();
                const name = picked.id.properties._boundaryName.getValue();
                if (type === 'township' && name) {
                    statFilters['township'] = name;
                    onFilterChange();
                    toast('已筛选乡镇：' + name);
                } else if (type === 'village' && name) {
                    statFilters['_village'] = name;
                    onFilterChange();
                    toast('已筛选村：' + name);
                }
            }
        } catch(e) {}
    }
}, Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK);

// ESC：优先关闭 3D/PDF 弹窗，否则整体重置。
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        const m3d = document.getElementById('model3dBox');
        const pdf = document.getElementById('pdfBox');
        if (m3d && m3d.style.display !== 'none' && m3d.classList.contains('open')) {
            close3DBox();
        } else if (pdf && pdf.style.display !== 'none') {
            closePdfBox();
        } else {
            resetAll();
        }
    }
});

// 移动端行为通过事件总线订阅，原函数不再被 monkey-patch。
(function _initMobileBus() {
    if (!window.Bus) return;

    Bus.on('chat:toggled', function (payload) {
        if (!_isMobile()) return;
        _syncMobileNav((payload && payload.open) ? 'chat' : 'map');
    });

    Bus.on('filter:changed', function () {
        if (typeof _mobileUpdateFilterBadge === 'function') _mobileUpdateFilterBadge();
    });

    Bus.on('info:closed', function () {
        if (_isMobile()) viewer.scene.requestRender();
    });
})();

initDashDrag();
initMapZoomSlider();
updateLayout();
viewer.scene.postRender.addEventListener(updateScaleBar);

(function syncHDToggle() {
    var cb = document.getElementById('hdModeToggle');
    if (cb) cb.checked = !!_hdMode;
})();

init();
