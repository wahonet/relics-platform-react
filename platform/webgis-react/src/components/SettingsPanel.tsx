import { useEffect, useState } from "react";
import { useUIStore } from "../stores/uiStore";
import { useHomeViewStore } from "../stores/homeViewStore";
import { flyTo, getViewer } from "../map/viewerRegistry";
import * as Cesium from "cesium";

interface ShandongAdmin {
  cities: {
    name: string;
    bbox?: [number, number, number, number];
    center?: [number, number];
    counties: {
      name: string;
      bbox?: [number, number, number, number];
      center?: [number, number];
    }[];
  }[];
}

let _shandongAdminCache: ShandongAdmin | null = null;
async function loadShandongAdmin(): Promise<ShandongAdmin | null> {
  if (_shandongAdminCache) return _shandongAdminCache;
  try {
    const r = await fetch("/static/data/shandong_admin.json?_=" + Date.now());
    if (!r.ok) return null;
    _shandongAdminCache = (await r.json()) as ShandongAdmin;
    return _shandongAdminCache;
  } catch {
    return null;
  }
}

export function SettingsPanel() {
  const open = useUIStore((s) => s.settingsPanelOpen);
  const setUI = useUIStore((s) => s.set);
  const homeView = useHomeViewStore((s) => s.view);
  const setHomeView = useHomeViewStore((s) => s.setView);
  const clearHomeView = useHomeViewStore((s) => s.clear);
  const hdMode = useUIStore((s) => s.hdMode);

  const [admin, setAdmin] = useState<ShandongAdmin | null>(null);
  const [city, setCity] = useState<string>(homeView?.city || "");
  const [county, setCounty] = useState<string>(homeView?.county || "");

  useEffect(() => {
    if (!open) return;
    loadShandongAdmin().then((d) => setAdmin(d));
  }, [open]);

  const cities = admin?.cities || [];
  const cityObj = cities.find((c) => c.name === city);
  const counties = cityObj?.counties || [];

  const applyHome = (cityName: string, countyName: string) => {
    if (!admin) return;
    const co = admin.cities.find((c) => c.name === cityName);
    if (!co) return;
    let center: [number, number] | undefined = co.center;
    let bbox: [number, number, number, number] | undefined = co.bbox;
    if (countyName) {
      const cn = co.counties.find((x) => x.name === countyName);
      if (cn) {
        center = cn.center || center;
        bbox = cn.bbox || bbox;
      }
    }
    if (!center && bbox) {
      center = [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2];
    }
    if (!center) return;
    let h = 75000;
    if (bbox) {
      const dx = (bbox[2] - bbox[0]) * 111000;
      const dy = (bbox[3] - bbox[1]) * 111000;
      h = Math.max(20000, Math.min(300000, Math.max(dx, dy) * 1.4));
    }
    setHomeView({ lng: center[0], lat: center[1], h, city: cityName, county: countyName });
    flyTo(center[0], center[1], h, 1.2);
  };

  const onCityChange = (next: string) => {
    setCity(next);
    setCounty("");
    if (next) applyHome(next, "");
  };
  const onCountyChange = (next: string) => {
    setCounty(next);
    if (city && next) applyHome(city, next);
  };

  const setCurrentAsHome = () => {
    const v = getViewer();
    if (!v) return;
    const pos = v.camera.positionCartographic;
    const lng = Cesium.Math.toDegrees(pos.longitude);
    const lat = Cesium.Math.toDegrees(pos.latitude);
    setHomeView({ lng, lat, h: pos.height, city, county });
    useUIStore.getState().showToast("已设置当前视角为主视角");
  };
  const restoreDefault = () => {
    clearHomeView();
    setCity("");
    setCounty("");
    const cfg = window.__PLATFORM_CONFIG;
    if (cfg?.geo?.center) {
      flyTo(cfg.geo.center.lng, cfg.geo.center.lat, cfg.geo.center.alt ?? 75000, 1.2);
    }
    useUIStore.getState().showToast("已恢复默认主视角");
  };

  const setHDMode = (val: boolean) => {
    useUIStore.getState().set({ hdMode: val });
    try {
      localStorage.setItem("hdMode", val ? "1" : "0");
    } catch {
      /* ignore */
    }
    const v = getViewer();
    if (v) {
      const dpr = window.devicePixelRatio || 1;
      if (val) {
        v.useBrowserRecommendedResolution = false;
        v.resolutionScale = Math.min(dpr, 2.0);
      } else {
        v.useBrowserRecommendedResolution = true;
        v.resolutionScale = dpr > 2 ? 1.5 : 1.0;
      }
      v.scene.requestRender();
    }
  };

  if (!open) return null;

  return (
    <>
      <div className="modal-mask" onClick={() => setUI({ settingsPanelOpen: false })} />
      <div className={"settings-panel" + (open ? " open" : "")}>
        <div
          className="modal-hdr"
          style={{ position: "sticky", top: 0, background: "rgba(13,17,23,.98)", zIndex: 2 }}
        >
          <h3>偏好设置</h3>
          <button onClick={() => setUI({ settingsPanelOpen: false })}>×</button>
        </div>
        <div className="sp-section">
          <h4>主视角 (Home View)</h4>
          <div className="sp-row">
            <span style={{ flex: "0 0 60px", color: "var(--t2)" }}>地市</span>
            <select
              style={{ flex: 1 }}
              value={city}
              onChange={(e) => onCityChange(e.target.value)}
            >
              <option value="">请选择...</option>
              {cities.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <div className="sp-row">
            <span style={{ flex: "0 0 60px", color: "var(--t2)" }}>区县</span>
            <select
              style={{ flex: 1 }}
              value={county}
              disabled={!city}
              onChange={(e) => onCountyChange(e.target.value)}
            >
              <option value="">{city ? "请选择..." : "请先选地市"}</option>
              {counties.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <div className="sp-row" style={{ gap: 8 }}>
            <button className="sp-button" onClick={setCurrentAsHome}>
              固化当前视角
            </button>
            <button className="sp-button" onClick={restoreDefault}>
              恢复默认
            </button>
          </div>
          {homeView ? (
            <div style={{ color: "var(--t2)", fontSize: 11, marginTop: 8 }}>
              当前主视角: {homeView.lng.toFixed(4)}, {homeView.lat.toFixed(4)} (h={Math.round(homeView.h)} m)
            </div>
          ) : null}
        </div>

        <div className="sp-section">
          <h4>渲染</h4>
          <label className="sp-row">
            <input
              type="checkbox"
              checked={hdMode}
              onChange={(e) => setHDMode(e.target.checked)}
            />
            高清模式（DPR 2x，画面更清晰，性能消耗更大）
          </label>
        </div>
      </div>
    </>
  );
}
