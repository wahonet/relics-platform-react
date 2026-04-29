import { useEffect, useRef, useState } from "react";
import * as Cesium from "cesium";
import { useUIStore } from "../stores/uiStore";
import {
  clearCache,
  estimateArea,
  fetchHistory,
  fetchProgress,
  openCacheFolder,
  startDownload,
  type TileDownloadProgress,
  type TileHistoryItem,
} from "../api/tiles";
import { getViewer } from "../map/viewerRegistry";

const ZOOMS = "12,13,14,15";
const PROVIDERS_DEFAULT = "arcgis_sat";

interface ShandongAdmin {
  cities: {
    name: string;
    bbox?: [number, number, number, number];
    counties: { name: string; bbox?: [number, number, number, number] }[];
  }[];
}

let _shandongAdminCache: ShandongAdmin | null = null;
async function loadAdmin(): Promise<ShandongAdmin | null> {
  if (_shandongAdminCache) return _shandongAdminCache;
  try {
    const r = await fetch("/static/data/shandong_admin.json");
    if (!r.ok) return null;
    _shandongAdminCache = (await r.json()) as ShandongAdmin;
    return _shandongAdminCache;
  } catch {
    return null;
  }
}

function fmtBytes(n: number): string {
  if (!n) return "0";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export function TileDownloadPanel() {
  const open = useUIStore((s) => s.tileDownloadOpen);
  const setUI = useUIStore((s) => s.set);

  const [mode, setMode] = useState<"bbox" | "county">("bbox");
  const [providers, setProviders] = useState(PROVIDERS_DEFAULT);
  const [zooms, setZooms] = useState(ZOOMS);
  const [admin, setAdmin] = useState<ShandongAdmin | null>(null);
  const [city, setCity] = useState<string>("");
  const [county, setCounty] = useState<string>("");
  const [estimate, setEstimate] = useState<{ total: number; cached: number; need: number } | null>(
    null,
  );
  const [progress, setProgress] = useState<TileDownloadProgress | null>(null);
  const [history, setHistory] = useState<TileHistoryItem[]>([]);
  const [drawing, setDrawing] = useState(false);
  const [selectedBbox, setSelectedBbox] = useState<
    [number, number, number, number] | null
  >(null);
  const drawHandlerRef = useRef<Cesium.ScreenSpaceEventHandler | null>(null);
  const drawEntityRef = useRef<Cesium.Entity | null>(null);

  useEffect(() => {
    if (!open) return;
    loadAdmin().then(setAdmin);
    fetchHistory(20).then((d) => setHistory(d.items || []));
    return () => stopDraw();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const cities = admin?.cities || [];
  const cityObj = cities.find((c) => c.name === city);
  const counties = cityObj?.counties || [];

  const bboxFromAdmin = (): [number, number, number, number] | null => {
    if (!cityObj) return null;
    if (county) {
      const co = cityObj.counties.find((x) => x.name === county);
      if (co?.bbox) return co.bbox;
    }
    return cityObj.bbox || null;
  };

  const currentBbox = mode === "bbox" ? selectedBbox : bboxFromAdmin();

  const labelStr =
    mode === "bbox"
      ? selectedBbox
        ? `框选区域 (${selectedBbox.map((x) => x.toFixed(3)).join(", ")})`
        : ""
      : `${city || ""}${county ? "·" + county : ""}`;

  useEffect(() => {
    if (!currentBbox) {
      setEstimate(null);
      return;
    }
    estimateArea(
      currentBbox[0],
      currentBbox[1],
      currentBbox[2],
      currentBbox[3],
      providers,
      zooms,
    )
      .then((d) => {
        if ("error" in d && d.error) {
          setEstimate(null);
        } else {
          setEstimate({ total: d.total, cached: d.cached, need: d.need });
        }
      })
      .catch(() => setEstimate(null));
  }, [currentBbox, providers, zooms]);

  const stopDraw = () => {
    if (drawHandlerRef.current) {
      drawHandlerRef.current.destroy();
      drawHandlerRef.current = null;
    }
    if (drawEntityRef.current) {
      const v = getViewer();
      if (v) v.entities.remove(drawEntityRef.current);
      drawEntityRef.current = null;
    }
    setDrawing(false);
  };

  const startDraw = () => {
    const v = getViewer();
    if (!v) return;
    stopDraw();
    setDrawing(true);
    setSelectedBbox(null);
    let startCart: Cesium.Cartographic | null = null;
    const handler = new Cesium.ScreenSpaceEventHandler(v.scene.canvas);
    drawHandlerRef.current = handler;
    handler.setInputAction((click: { position: Cesium.Cartesian2 }) => {
      const cart = v.camera.pickEllipsoid(click.position);
      if (!cart) return;
      const c = Cesium.Cartographic.fromCartesian(cart);
      if (!startCart) {
        startCart = c;
      } else {
        const lng1 = Math.min(
          Cesium.Math.toDegrees(startCart.longitude),
          Cesium.Math.toDegrees(c.longitude),
        );
        const lng2 = Math.max(
          Cesium.Math.toDegrees(startCart.longitude),
          Cesium.Math.toDegrees(c.longitude),
        );
        const lat1 = Math.min(
          Cesium.Math.toDegrees(startCart.latitude),
          Cesium.Math.toDegrees(c.latitude),
        );
        const lat2 = Math.max(
          Cesium.Math.toDegrees(startCart.latitude),
          Cesium.Math.toDegrees(c.latitude),
        );
        setSelectedBbox([lng1, lat1, lng2, lat2]);
        stopDraw();
      }
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

    handler.setInputAction((mv: { endPosition: Cesium.Cartesian2 }) => {
      if (!startCart) return;
      const cart = v.camera.pickEllipsoid(mv.endPosition);
      if (!cart) return;
      const c = Cesium.Cartographic.fromCartesian(cart);
      const lng1 = Cesium.Math.toDegrees(startCart.longitude);
      const lng2 = Cesium.Math.toDegrees(c.longitude);
      const lat1 = Cesium.Math.toDegrees(startCart.latitude);
      const lat2 = Cesium.Math.toDegrees(c.latitude);
      const positions = Cesium.Cartesian3.fromDegreesArray([
        Math.min(lng1, lng2),
        Math.min(lat1, lat2),
        Math.max(lng1, lng2),
        Math.min(lat1, lat2),
        Math.max(lng1, lng2),
        Math.max(lat1, lat2),
        Math.min(lng1, lng2),
        Math.max(lat1, lat2),
      ]);
      if (!drawEntityRef.current) {
        drawEntityRef.current = v.entities.add({
          polygon: {
            hierarchy: new Cesium.PolygonHierarchy(positions),
            material: Cesium.Color.fromCssColorString("rgba(88,166,255,0.18)"),
            outline: true,
            outlineColor: Cesium.Color.fromCssColorString("rgba(88,166,255,0.7)"),
            height: 0,
          },
        });
      } else {
        drawEntityRef.current.polygon!.hierarchy = new Cesium.ConstantProperty(
          new Cesium.PolygonHierarchy(positions),
        );
      }
    }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);
  };

  const startJob = async () => {
    if (!currentBbox) return;
    try {
      const job = await startDownload(
        currentBbox[0],
        currentBbox[1],
        currentBbox[2],
        currentBbox[3],
        providers,
        zooms,
        labelStr,
      );
      setProgress({
        id: job.job_id,
        status: "running",
        total: job.total,
        skipped: job.skipped,
        need: job.need,
        downloaded: 0,
        failed: 0,
        bytes: 0,
      } as TileDownloadProgress);
      const poll = async () => {
        try {
          const p = await fetchProgress(job.job_id);
          setProgress(p);
          if (p.status === "running") {
            setTimeout(poll, 1500);
          } else {
            useUIStore.getState().showToast(`下载完成: ${p.downloaded} 张, 失败 ${p.failed}`);
            const h = await fetchHistory(20);
            setHistory(h.items || []);
          }
        } catch {
          /* ignore */
        }
      };
      setTimeout(poll, 800);
    } catch (e) {
      useUIStore.getState().showToast("下载启动失败: " + String(e));
    }
  };

  if (!open) return null;

  const pct =
    progress && progress.need > 0
      ? Math.min(
          100,
          Math.round(((progress.downloaded + progress.failed) / progress.need) * 100),
        )
      : 0;

  return (
    <>
      <div className="modal-mask" onClick={() => setUI({ tileDownloadOpen: false })} />
      <div className="tile-panel">
        <div className="tile-hdr">
          <h3>离线瓦片下载</h3>
          <button className="modal-hdr-x" onClick={() => setUI({ tileDownloadOpen: false })}>
            ×
          </button>
        </div>
        <div className="tile-body">
          <div className="tile-row">
            <label>范围模式</label>
            <select
              value={mode}
              onChange={(e) => {
                setMode(e.target.value as "bbox" | "county");
                stopDraw();
                setSelectedBbox(null);
              }}
            >
              <option value="bbox">地图框选</option>
              <option value="county">按县域选择</option>
            </select>
          </div>
          {mode === "county" ? (
            <>
              <div className="tile-row">
                <label>地市</label>
                <select value={city} onChange={(e) => setCity(e.target.value)}>
                  <option value="">请选择...</option>
                  {cities.map((c) => (
                    <option key={c.name} value={c.name}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="tile-row">
                <label>区县</label>
                <select
                  value={county}
                  disabled={!city}
                  onChange={(e) => setCounty(e.target.value)}
                >
                  <option value="">{city ? "请选择..." : "请先选地市"}</option>
                  {counties.map((c) => (
                    <option key={c.name} value={c.name}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>
            </>
          ) : (
            <div className="tile-row">
              <label>地图</label>
              <button className="sp-button" onClick={startDraw} disabled={drawing}>
                {drawing ? "请在地图上点击两次画矩形..." : "在地图上框选"}
              </button>
              {selectedBbox ? (
                <span style={{ fontSize: 12, color: "var(--t2)", marginLeft: 6 }}>
                  ✓ 已框选
                </span>
              ) : null}
            </div>
          )}
          <div className="tile-row">
            <label>影像源</label>
            <select value={providers} onChange={(e) => setProviders(e.target.value)}>
              <option value="arcgis_sat">ArcGIS 影像</option>
              <option value="osm">OSM 矢量</option>
              <option value="arcgis_sat,osm">影像 + 矢量</option>
              <option value="gaode_sat,gaode_anno">高德影像 + 标注</option>
            </select>
          </div>
          <div className="tile-row">
            <label>层级</label>
            <input
              type="text"
              value={zooms}
              onChange={(e) => setZooms(e.target.value)}
              placeholder="12,13,14,15"
            />
          </div>

          {estimate ? (
            <div style={{ color: "var(--t2)", fontSize: 12, padding: "6px 0" }}>
              预估: 总 <b style={{ color: "var(--accent)" }}>{estimate.total}</b> 张, 已缓存{" "}
              <b style={{ color: "var(--green)" }}>{estimate.cached}</b>, 待下载{" "}
              <b style={{ color: "var(--yellow)" }}>{estimate.need}</b>
            </div>
          ) : null}

          {progress ? (
            <div style={{ marginTop: 10 }}>
              <div className="tile-progress">
                <div className="tile-progress-bar" style={{ width: `${pct}%` }} />
              </div>
              <div style={{ color: "var(--t2)", fontSize: 11, marginTop: 4 }}>
                {progress.status === "running" ? "下载中" : "已完成"}: 已下载{" "}
                <b style={{ color: "var(--green)" }}>{progress.downloaded}</b> / {progress.need}, 失败{" "}
                <b style={{ color: "var(--red)" }}>{progress.failed}</b>, 已缓存命中 {progress.skipped},
                体积 {fmtBytes(progress.bytes)}
              </div>
            </div>
          ) : null}

          <div className="tile-row" style={{ marginTop: 12, gap: 8 }}>
            <button
              className="sp-button primary"
              onClick={startJob}
              disabled={!currentBbox || progress?.status === "running"}
            >
              {progress?.status === "running" ? "下载中..." : "开始下载"}
            </button>
            <button className="sp-button" onClick={() => openCacheFolder()}>
              打开缓存文件夹
            </button>
            <button
              className="sp-button"
              onClick={async () => {
                if (!confirm("确定清空所有离线瓦片缓存?")) return;
                await clearCache();
                useUIStore.getState().showToast("缓存已清空");
                const h = await fetchHistory(20);
                setHistory(h.items || []);
              }}
            >
              清空缓存
            </button>
          </div>
        </div>
        <div className="tile-history">
          <h4>最近下载历史</h4>
          {history.length === 0 ? (
            <div style={{ color: "var(--t2)", fontSize: 11 }}>暂无下载记录</div>
          ) : (
            history.map((h) => (
              <div key={h.id} className="tile-hist-item">
                {h.label || "(无标签)"} · {h.providers?.join(",")} · z={h.zooms?.join(",")} · 下载{" "}
                {h.downloaded} / 失败 {h.failed} · {fmtBytes(h.bytes)} ·{" "}
                {h.finished_at
                  ? new Date(h.finished_at * 1000).toLocaleString()
                  : "进行中"}
              </div>
            ))
          )}
        </div>
      </div>
    </>
  );
}
