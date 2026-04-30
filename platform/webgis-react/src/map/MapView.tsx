import { useEffect, useRef } from "react";
import * as Cesium from "cesium";
import { useCesiumViewer } from "./useCesiumViewer";
import { applyBaseLayer, setBaseLayerAlpha } from "./baseLayer";
import { setTerrainEnabled } from "./terrain";
import { PointRenderer } from "./PointRenderer";
import { ViewportManager } from "./ViewportManager";
import { BoundaryLayer } from "./BoundaryLayer";
import { OfflineCoverageLayer } from "./OfflineCoverageLayer";
import { useUIStore } from "../stores/uiStore";
import { useFilterStore } from "../stores/filterStore";
import { useRelicsStore } from "../stores/relicsStore";
import { useHomeViewStore } from "../stores/homeViewStore";
import { fetchRelicDetail } from "../api/relics";

interface MapViewProps {
  onCompassRotate?: (deg: number) => void;
  onScaleUpdate?: (label: string) => void;
}

export function MapView({ onCompassRotate, onScaleUpdate }: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useCesiumViewer(containerRef);

  const pointRendererRef = useRef<PointRenderer | null>(null);
  const viewportRef = useRef<ViewportManager | null>(null);
  const boundaryRef = useRef<BoundaryLayer | null>(null);
  const offlineCoverageRef = useRef<OfflineCoverageLayer | null>(null);

  const baseLayer = useUIStore((s) => s.baseLayer);
  const baseLayerAlpha = useUIStore((s) => s.baseLayerAlpha);
  const terrainEnabled = useUIStore((s) => s.terrainEnabled);
  const bndCounty = useUIStore((s) => s.bndCounty);
  const bndTownship = useUIStore((s) => s.bndTownship);
  const bndVillage = useUIStore((s) => s.bndVillage);
  const bndVillageName = useUIStore((s) => s.bndVillageName);
  const setUI = useUIStore((s) => s.set);

  const allRelicsLen = useRelicsStore((s) => s.all.length);
  // 拆成原始值订阅,避免 selector 每次返回新对象引发无限渲染。
  const filterActiveCats = useFilterStore((s) => s.activeCats);
  const filterTownship = useFilterStore((s) => s.township);
  const filterLevel = useFilterStore((s) => s.level);
  const filterStatFilters = useFilterStore((s) => s.statFilters);

  const homeView = useHomeViewStore((s) => s.view);
  const offlineTick = useUIStore((s) => s.offlineCoverageTick);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    const renderer = new PointRenderer(viewer);
    const viewport = new ViewportManager(viewer, renderer);
    const boundary = new BoundaryLayer(viewer);
    const offlineCoverage = new OfflineCoverageLayer(viewer);

    pointRendererRef.current = renderer;
    viewportRef.current = viewport;
    boundaryRef.current = boundary;
    offlineCoverageRef.current = offlineCoverage;

    renderer.setOnPick(async (code: string) => {
      try {
        const r = useRelicsStore.getState().byCode.get(code);
        if (r) {
          setUI({ selectedRelic: r });
          return;
        }
        const full = await fetchRelicDetail(code);
        if (full?.archive_code) setUI({ selectedRelic: full });
      } catch {
        /* ignore */
      }
    });

    boundary.load().then(() => {
      const ui = useUIStore.getState();
      boundary.setVisibility({
        county: ui.bndCounty,
        township: ui.bndTownship,
        village: ui.bndVillage,
        villageName: ui.bndVillageName,
      });
    });

    viewport.start((count, truncated) => {
      if (truncated) {
        useUIStore.getState().showToast(`视口内文物较多,仅显示前 ${count} 处`);
      }
    });

    const onPreRender = () => {
      const headDeg = -Cesium.Math.toDegrees(viewer.camera.heading);
      onCompassRotate?.(headDeg);
    };
    const onPostRender = () => {
      try {
        const canvas = viewer.canvas;
        const cx = canvas.clientWidth / 2;
        const cy = canvas.clientHeight / 2;
        const left = viewer.camera.pickEllipsoid(new Cesium.Cartesian2(cx - 50, cy));
        const right = viewer.camera.pickEllipsoid(new Cesium.Cartesian2(cx + 50, cy));
        if (!left || !right) return;
        const dist = Cesium.Cartesian3.distance(left, right);
        const mpp = dist / 100;
        const dpi = window.devicePixelRatio * 96;
        const mPerPx = 0.0254 / dpi;
        const ratio = Math.round(mpp / mPerPx);
        const nice = [
          500, 1000, 2000, 2500, 5000, 10000, 15000, 20000, 25000, 50000, 100000,
          150000, 200000, 250000, 500000, 1000000, 2000000, 5000000,
        ];
        let best = ratio;
        for (const n of nice) {
          if (n >= ratio * 0.8) {
            best = n;
            break;
          }
        }
        onScaleUpdate?.(`1 : ${best.toLocaleString()}`);
      } catch {
        /* ignore */
      }
    };
    viewer.scene.preRender.addEventListener(onPreRender);
    viewer.scene.postRender.addEventListener(onPostRender);

    return () => {
      // 注意:在 React 18 StrictMode + hook 依赖链下,父级 useCesiumViewer 的
      // cleanup (viewer.destroy()) 可能比这个 cleanup 更早跑,导致 viewer 已死。
      // 所以全部访问都要保护。
      try {
        if (!viewer.isDestroyed()) {
          viewer.scene.preRender.removeEventListener(onPreRender);
          viewer.scene.postRender.removeEventListener(onPostRender);
        }
      } catch {
        /* ignore */
      }
      viewport.stop();
      renderer.destroy();
      try {
        offlineCoverage.clear();
      } catch {
        /* ignore */
      }
      pointRendererRef.current = null;
      viewportRef.current = null;
      boundaryRef.current = null;
      offlineCoverageRef.current = null;
    };
  }, [viewerRef, onCompassRotate, onScaleUpdate, setUI]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    applyBaseLayer(viewer, baseLayer, baseLayerAlpha);

    // 切到"离线影像 / 离线矢量"时,把已下载区域的 bbox 用红框标识在地图上,
    // 让用户一眼看到能滑过去的区域;切到其它底图时清掉。
    const cov = offlineCoverageRef.current;
    if (!cov) return;
    if (baseLayer === "arcgis_sat" || baseLayer === "osm") {
      cov.refresh().then((n) => {
        if (n > 0) {
          useUIStore.getState().showToast(`已加载 ${n} 个离线下载区域 (红色框)`);
        }
      });
    } else {
      cov.clear();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewerRef, baseLayer, offlineTick]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    setBaseLayerAlpha(viewer, baseLayerAlpha);
  }, [viewerRef, baseLayerAlpha]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    setTerrainEnabled(viewer, terrainEnabled);
  }, [viewerRef, terrainEnabled]);

  useEffect(() => {
    const b = boundaryRef.current;
    if (!b) return;
    b.setVisibility({
      county: bndCounty,
      township: bndTownship,
      village: bndVillage,
      villageName: bndVillageName,
    });
  }, [bndCounty, bndTownship, bndVillage, bndVillageName]);

  useEffect(() => {
    const vm = viewportRef.current;
    if (!vm) return;
    const allCatNames = new Set(
      useRelicsStore
        .getState()
        .all.map((r) => r.category_main)
        .filter(Boolean) as string[],
    );
    const backend = useFilterStore.getState().toBackend(allCatNames);
    vm.setFilters(backend);
  }, [
    filterActiveCats,
    filterTownship,
    filterLevel,
    filterStatFilters,
    allRelicsLen,
  ]);

  const homeAppliedRef = useRef(false);
  useEffect(() => {
    if (homeAppliedRef.current) return;
    const viewer = viewerRef.current;
    if (!viewer || !homeView) return;
    viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(homeView.lng, homeView.lat, homeView.h),
      orientation: { heading: 0, pitch: Cesium.Math.toRadians(-90), roll: 0 },
      duration: 0,
    });
    homeAppliedRef.current = true;
  }, [viewerRef, homeView]);

  return <div ref={containerRef} className="map-container" />;
}

export function flyHomeFn(viewer: Cesium.Viewer | null): void {
  if (!viewer) return;
  const home = useHomeViewStore.getState().view;
  const cfg = window.__PLATFORM_CONFIG;
  const dest = home || {
    lng: cfg?.geo?.center?.lng ?? 116.34,
    lat: cfg?.geo?.center?.lat ?? 35.41,
    h: cfg?.geo?.center?.alt ?? 75000,
  };
  viewer.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(dest.lng, dest.lat, dest.h),
    orientation: { heading: 0, pitch: Cesium.Math.toRadians(-90), roll: 0 },
    duration: 1.2,
  });
}
