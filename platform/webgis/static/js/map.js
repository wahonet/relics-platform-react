// Cesium 地图初始化、底图管理、指北针与比例尺。
// Ion Token 由后端 /api/platform/config 注入；未配置时自动回退到本地 DEM。
if (window.__PLATFORM_CONFIG && window.__PLATFORM_CONFIG.cesium_ion_token) {
    Cesium.Ion.defaultAccessToken = window.__PLATFORM_CONFIG.cesium_ion_token;
}

const viewer = new Cesium.Viewer('cesiumContainer', {
    baseLayerPicker: false, geocoder: false, homeButton: false,
    sceneModePicker: false, navigationHelpButton: false,
    animation: false, timeline: false, fullscreenButton: false,
    selectionIndicator: false, infoBox: false,
    baseLayer: false,
    terrainProvider: new Cesium.EllipsoidTerrainProvider(),
});

viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString('#0d1117');
viewer.scene.backgroundColor = Cesium.Color.fromCssColorString('#0d1117');
viewer.scene.postProcessStages.fxaa.enabled = true;

// Phase B1 止血：requestRenderMode 让空闲时不重绘（CPU 从 20-30% 降到 <5%）；
// maximumRenderTimeChange=0.5 保留对光照/地形等时间相关变化的响应。
viewer.scene.requestRenderMode = true;
viewer.scene.maximumRenderTimeChange = 0.5;

// 高 DPR 设备（手机）下 resolutionScale 降档，避免 4K 渲染压垮 GPU。
function applyHDRendering() {
    var dpr = window.devicePixelRatio || 1;
    if (_hdMode) {
        viewer.useBrowserRecommendedResolution = false;
        viewer.resolutionScale = Math.min(dpr, 2.0);
    } else {
        viewer.useBrowserRecommendedResolution = true;
        viewer.resolutionScale = dpr > 2 ? 1.5 : 1.0;
    }
    viewer.scene.requestRender();
}
applyHDRendering();

// 相机距离约束：近处防穿模，远处收敛到"覆盖山东全省"量级。
// (以前按 config.geo.bounds 对角线算,只能看县域;用户现在可以改主视角到
//  任一山东市/县,所以统一把上限设为 500km,够看到整个山东省,也不至于拉到看全球。)
(function _applyCameraConstraints() {
    var scc = viewer.scene.screenSpaceCameraController;
    scc.minimumZoomDistance = 10;
    scc.maximumZoomDistance = 500000;
})();

viewer.scene.fog.enabled = false;
viewer.scene.globe.showGroundAtmosphere = false;
viewer.scene.skyAtmosphere.show = false;
viewer.scene.verticalExaggeration = 1.0;
viewer.scene.verticalExaggerationRelativeHeight = 0.0;

// 地形默认关闭，勾选后优先拉 Ion，失败再走 /api/terrain 本地 DEM。
const _flatTerrain = new Cesium.EllipsoidTerrainProvider();
let _terrainEnabled = false;
let _terrainProvider = null;

// 视角模式：'2d' = 正射俯视（pitch=-90，锁定倾斜）；'3d' = 斜视。
// 默认 2D 看起来更像普通 GIS 地图，勾选地形时会自动进入 3D。
let _viewMode = '2d';

function _applyViewModeConstraint() {
    var scc = viewer.scene.screenSpaceCameraController;
    if (_viewMode === '2d') {
        scc.enableTilt = false;
        scc.enableLook = false;
    } else {
        scc.enableTilt = true;
        scc.enableLook = true;
    }
}

function setViewMode(mode) {
    _viewMode = mode === '3d' ? '3d' : '2d';
    _applyViewModeConstraint();
    var pos = viewer.camera.positionCartographic;
    var pitch = _viewMode === '2d' ? Cesium.Math.toRadians(-90) : Cesium.Math.toRadians(-45);
    viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(
            Cesium.Math.toDegrees(pos.longitude),
            Cesium.Math.toDegrees(pos.latitude),
            pos.height
        ),
        orientation: { heading: viewer.camera.heading, pitch: pitch, roll: 0 },
        duration: 0.8,
    });
    viewer.scene.requestRender();
}
_applyViewModeConstraint();

function toggleTerrain() {
    var cb = document.getElementById('terrainToggle');
    _terrainEnabled = cb.checked;
    if (_terrainEnabled) {
        // 勾选地形时自动进入 3D 斜视视角。
        _viewMode = '3d';
        _applyViewModeConstraint();
        viewer.scene.verticalExaggeration = 5.0;
        viewer.scene.maximumRenderTimeChange = 0.5;
        if (_terrainProvider) {
            viewer.terrainProvider = _terrainProvider;
        } else {
            Cesium.CesiumTerrainProvider.fromIonAssetId(1).then(function (tp) {
                _terrainProvider = tp;
                if (_terrainEnabled) {
                    viewer.terrainProvider = tp;
                    viewer.scene.requestRender();
                }
                console.log('[DEM] Ion terrain loaded');
            }).catch(function () {
                console.warn('[DEM] Ion terrain failed, trying local DEM');
                var local = new Cesium.CustomHeightmapTerrainProvider({
                    width: 65, height: 65,
                    tilingScheme: new Cesium.GeographicTilingScheme(),
                    callback: function (x, y, level) {
                        return fetch('/api/terrain/' + level + '/' + x + '/' + y)
                            .then(function (r) {
                                if (!r.ok) return new Float32Array(65 * 65);
                                return r.arrayBuffer().then(function (b) { return new Float32Array(b); });
                            })
                            .catch(function () { return new Float32Array(65 * 65); });
                    },
                });
                _terrainProvider = local;
                if (_terrainEnabled) {
                    viewer.terrainProvider = local;
                    viewer.scene.requestRender();
                }
            });
        }
        var pos = viewer.camera.positionCartographic;
        viewer.camera.flyTo({
            destination: Cesium.Cartesian3.fromDegrees(
                Cesium.Math.toDegrees(pos.longitude),
                Cesium.Math.toDegrees(pos.latitude),
                pos.height
            ),
            orientation: { heading: viewer.camera.heading, pitch: Cesium.Math.toRadians(-45), roll: 0 },
            duration: 1.0,
        });
    } else {
        viewer.terrainProvider = _flatTerrain;
        viewer.scene.verticalExaggeration = 1.0;
        viewer.scene.maximumRenderTimeChange = Infinity;
        // 取消地形时回到 2D 正射俯视视角。
        _viewMode = '2d';
        _applyViewModeConstraint();
        var pos0 = viewer.camera.positionCartographic;
        viewer.camera.flyTo({
            destination: Cesium.Cartesian3.fromDegrees(
                Cesium.Math.toDegrees(pos0.longitude),
                Cesium.Math.toDegrees(pos0.latitude),
                pos0.height
            ),
            orientation: { heading: viewer.camera.heading, pitch: Cesium.Math.toRadians(-90), roll: 0 },
            duration: 0.8,
        });
    }
    viewer.scene.requestRender();
    console.log('[DEM] terrain ' + (_terrainEnabled ? 'ON (×5)' : 'OFF'));
}

// 启动时如果用户已经把某个县固化为"主视角"(home_view.js/localStorage),
// 就直接落在那里;否则用 config 默认 CENTER。
(function _initialFly() {
    let dest = { lng: CENTER.lng, lat: CENTER.lat, h: CENTER.h };
    try {
        const raw = localStorage.getItem('relics.homeView');
        if (raw) {
            const hv = JSON.parse(raw);
            if (hv && typeof hv.lng === 'number' && typeof hv.lat === 'number') {
                dest = { lng: hv.lng, lat: hv.lat, h: hv.h || CENTER.h };
            }
        }
    } catch (e) {}
    viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(dest.lng, dest.lat, dest.h),
        orientation: { heading: 0, pitch: Cesium.Math.toRadians(-90), roll: 0 },
        duration: 0,
    });
})();

let currentBaseType = 'arcgis_sat';

// 离线的两项不许回源,上游 tile_proxy 见到 ?offline=1 会直接返回 1x1 透明 PNG,
// 满足"默认离线地图应该是完全空白"的需求 —— 只有通过下载模块入库的瓦片才会被显示。
// 在线项(gaode_*)仍然走 /tiles 代理,以便顺带写入离线缓存。
const OFFLINE_ONLY_BASES = new Set(['arcgis_sat', 'osm']);

// 多源叠加：卫星影像单独要挂一层中文标注(gaode_anno),否则看上去没地名。
const ONLINE_BASE_LAYOUT = {
    gaode_sat: { base: 'gaode_sat', overlay: 'gaode_anno' },
    gaode_vec: { base: 'gaode_vec', overlay: null },
};

function _tileUrl(type, opts) {
    // `?offline=1` 让后端跳过上游,`?t=<ts>` 用于下载完成后破坏旧的空白响应缓存。
    const qs = [];
    if (OFFLINE_ONLY_BASES.has(type)) qs.push('offline=1');
    if (opts && opts.bust) qs.push('t=' + Date.now());
    const suffix = qs.length ? ('?' + qs.join('&')) : '';
    return '/tiles/' + type + '/{z}/{x}/{y}' + suffix;
}

function makeImageryLayer(url) {
    return new Cesium.ImageryLayer(
        new Cesium.UrlTemplateImageryProvider({ url, maximumLevel: 18 })
    );
}

function switchBaseLayer(type) {
    currentBaseType = type;
    try { viewer.imageryLayers.removeAll(); } catch(e) {}

    if (type === 'none') {
        viewer.scene.requestRender();
        return;
    }

    const alpha = parseFloat(document.getElementById('baseAlpha').value) / 100;
    const layout = ONLINE_BASE_LAYOUT[type] || { base: type, overlay: null };

    try {
        const base = viewer.imageryLayers.add(
            // bust=true 让重复点同一个底图(例如下载完成后刷新)时,
            // 浏览器和 Cesium 不会把以前的"空白瓦片"拿出来糊弄我们。
            makeImageryLayer(_tileUrl(layout.base, { bust: true }))
        );
        base.alpha = alpha;

        if (layout.overlay && !OFFLINE_ONLY_BASES.has(layout.overlay)) {
            const over = viewer.imageryLayers.add(
                makeImageryLayer(_tileUrl(layout.overlay, { bust: true }))
            );
            over.alpha = 1.0;
        }
    } catch(e) {
        console.error('底图加载失败:', e);
    }
    viewer.scene.requestRender();
}
switchBaseLayer('arcgis_sat');
setBaseMapAlpha(90);

function setBaseMapAlpha(val) {
    const alpha = parseFloat(val) / 100;
    for (let i = 0; i < viewer.imageryLayers.length; i++) {
        viewer.imageryLayers.get(i).alpha = alpha;
    }
    document.getElementById('baseAlphaVal').textContent = val + '%';
    viewer.scene.requestRender();
}

viewer.scene.preRender.addEventListener(() => {
    const ring = document.getElementById('compassRing');
    if (ring) ring.style.transform = 'rotate(' + (-Cesium.Math.toDegrees(viewer.camera.heading)) + 'deg)';
});

function resetNorthView() {
    const pos = viewer.camera.positionCartographic;
    viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(
            Cesium.Math.toDegrees(pos.longitude),
            Cesium.Math.toDegrees(pos.latitude),
            pos.height
        ),
        orientation: { heading: 0, pitch: viewer.camera.pitch, roll: 0 },
        duration: 0.8,
    });
}

// 自定义缩放：禁用 Cesium 默认滚轮缩放，改用指数插值保证近处/远处手感一致。
viewer.scene.screenSpaceCameraController.zoomEventTypes = [];
viewer.scene.canvas.addEventListener('wheel', function(e) {
    e.preventDefault();
    const cam = viewer.camera;
    const height = cam.positionCartographic.height;
    const factor = e.deltaY > 0 ? 1.08 : 0.93;
    const newH = Math.max(80, Math.min(500000, height * factor));
    cam.moveForward(height - newH);
    updateMapZoomSlider();
}, { passive: false });

function getMapZoomLevel() {
    return viewer.camera.positionCartographic.height;
}

function mapZoomTo(h) {
    const cam = viewer.camera;
    const cur = cam.positionCartographic.height;
    cam.moveForward(cur - h);
}

function updateMapZoomSlider() {
    const thumb = document.getElementById('mapZoomThumb');
    const fill = document.getElementById('mapZoomFill');
    const label = document.getElementById('mapZoomLabel');
    if (!thumb) return;
    const h = getMapZoomLevel();
    const minH = Math.log(80), maxH = Math.log(500000);
    const pct = 1 - (Math.log(Math.max(80, Math.min(500000, h))) - minH) / (maxH - minH);
    thumb.style.bottom = (pct * 100) + '%';
    fill.style.height = (pct * 100) + '%';
    if (h > 10000) label.textContent = (h / 1000).toFixed(0) + 'km';
    else if (h > 1000) label.textContent = (h / 1000).toFixed(1) + 'km';
    else label.textContent = h.toFixed(0) + 'm';
}

function mapZoomStep(dir) {
    const h = getMapZoomLevel();
    const factor = dir > 0 ? 1.4 : 0.71;
    const newH = Math.max(80, Math.min(500000, h * factor));
    mapZoomTo(newH);
    updateMapZoomSlider();
}

function initMapZoomSlider() {
    const track = document.getElementById('mapZoomTrack');
    if (!track) return;
    let dragging = false;
    function applyY(clientY) {
        const rect = track.getBoundingClientRect();
        const pct = 1 - Math.max(0, Math.min(1, (clientY - rect.top) / rect.height));
        const minH = Math.log(80), maxH = Math.log(500000);
        const h = Math.exp(minH + pct * (maxH - minH));
        mapZoomTo(h);
        updateMapZoomSlider();
    }
    track.addEventListener('pointerdown', function(e) {
        dragging = true; track.setPointerCapture(e.pointerId); applyY(e.clientY);
    });
    track.addEventListener('pointermove', function(e) { if (dragging) applyY(e.clientY); });
    track.addEventListener('pointerup', function(e) { dragging = false; });

    viewer.scene.postRender.addEventListener(updateMapZoomSlider);
}

function updateScaleBar() {
    const label = document.getElementById('scaleBarLabel');
    if (!label) return;
    try {
        const canvas = viewer.canvas;
        const cx = canvas.clientWidth / 2, cy = canvas.clientHeight / 2;
        const left = viewer.camera.pickEllipsoid(new Cesium.Cartesian2(cx - 50, cy));
        const right = viewer.camera.pickEllipsoid(new Cesium.Cartesian2(cx + 50, cy));
        if (!left || !right) return;
        const dist = Cesium.Cartesian3.distance(left, right);
        const mpp = dist / 100;
        const dpi = window.devicePixelRatio * 96;
        const mPerPx = 0.0254 / dpi;
        const ratio = Math.round(mpp / mPerPx);
        const nice = [500,1000,2000,2500,5000,10000,15000,20000,25000,50000,100000,150000,200000,250000,500000,1000000,2000000,5000000];
        let best = ratio;
        for (const n of nice) { if (n >= ratio * 0.8) { best = n; break; } }
        label.textContent = '1 : ' + best.toLocaleString();
    } catch(e) {}
}
