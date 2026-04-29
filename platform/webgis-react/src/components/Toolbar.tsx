import { useEffect, useRef, useState } from "react";
import { useUIStore } from "../stores/uiStore";
import { useFilterStore } from "../stores/filterStore";
import { useRelicsStore } from "../stores/relicsStore";
import { flyHomeFn } from "../map/MapView";
import { getViewer } from "../map/viewerRegistry";
import type { BaseLayerType } from "../types";

const BASE_OPTIONS: { value: BaseLayerType; label: string }[] = [
  { value: "arcgis_sat", label: "离线影像" },
  { value: "osm", label: "离线矢量" },
  { value: "gaode_sat", label: "在线影像 (高德)" },
  { value: "gaode_vec", label: "在线矢量 (高德)" },
  { value: "none", label: "无底图" },
];

export function Toolbar() {
  const ui = useUIStore();
  const filteredCount = useFilterStore((s) => s.activeCats.size);
  const allCount = useRelicsStore((s) => s.all.length);

  const [baseMenuOpen, setBaseMenuOpen] = useState(false);
  const [boundaryMenuOpen, setBoundaryMenuOpen] = useState(false);
  const baseMenuRef = useRef<HTMLDivElement>(null);
  const boundaryMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      const t = e.target as Node;
      if (baseMenuRef.current && !baseMenuRef.current.contains(t)) {
        setBaseMenuOpen(false);
      }
      if (boundaryMenuRef.current && !boundaryMenuRef.current.contains(t)) {
        setBoundaryMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const baseLabel =
    BASE_OPTIONS.find((o) => o.value === ui.baseLayer)?.label || "底图影像";

  const onReset = () => {
    const cats = useRelicsStore.getState().all.map((r) => r.category_main || "");
    useFilterStore.getState().reset(new Set(cats.filter(Boolean)));
    ui.set({
      filterPanelOpen: false,
      routePanelOpen: false,
      chatPanelOpen: false,
      worklogOpen: false,
      selectedRelic: null,
    });
    flyHomeFn(getViewer());
    setTimeout(() => flyHomeFn(getViewer()), 50);
    ui.showToast("已重置筛选并飞回主视角");
  };

  const onFullscreen = () => {
    if (!document.fullscreenElement) document.documentElement.requestFullscreen();
    else document.exitFullscreen();
  };

  return (
    <div className="toolbar">
      <div className="tb-group boxed">
        <button
          className={"tb" + (ui.filterPanelOpen ? " on" : "")}
          onClick={() => ui.set({ filterPanelOpen: !ui.filterPanelOpen })}
          title="筛选面板"
        >
          <svg viewBox="0 0 24 24">
            <path d="M3 4h18v2L13 16v6h-2v-6L3 6V4z" />
          </svg>
          筛选
          {filteredCount > 0 && filteredCount < allCount ? <b>·{filteredCount}</b> : null}
        </button>
      </div>

      <div className="tb-group boxed">
        <div ref={baseMenuRef} style={{ position: "relative" }}>
          <button
            className={"tb" + (baseMenuOpen ? " on" : "")}
            onClick={() => setBaseMenuOpen((v) => !v)}
          >
            <svg viewBox="0 0 24 24">
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
            </svg>
            {baseLabel} ▾
          </button>
          {baseMenuOpen && (
            <div
              className="dropdown-menu open"
              style={{ left: 0, top: "calc(100% + 4px)" }}
            >
              {BASE_OPTIONS.map((opt) => (
                <div
                  key={opt.value}
                  className={
                    "dropdown-item" + (ui.baseLayer === opt.value ? " on" : "")
                  }
                  onClick={() => {
                    ui.set({ baseLayer: opt.value });
                    setBaseMenuOpen(false);
                  }}
                >
                  {opt.label}
                </div>
              ))}
              <div className="dropdown-divider" />
              <div className="dropdown-group">底图透明度: {ui.baseLayerAlpha}%</div>
              <input
                type="range"
                min={20}
                max={100}
                value={ui.baseLayerAlpha}
                onChange={(e) => ui.set({ baseLayerAlpha: Number(e.target.value) })}
                style={{ width: "calc(100% - 16px)", margin: "4px 8px" }}
              />
            </div>
          )}
        </div>
        <button
          className={"tb" + (ui.tileDownloadOpen ? " on" : "")}
          onClick={() => ui.set({ tileDownloadOpen: !ui.tileDownloadOpen })}
        >
          <svg viewBox="0 0 24 24">
            <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z" />
          </svg>
          下载地图
        </button>
      </div>

      <div className="tb-group boxed">
        <div ref={boundaryMenuRef} style={{ position: "relative" }}>
          <button
            className={"tb" + (boundaryMenuOpen ? " on" : "")}
            onClick={() => setBoundaryMenuOpen((v) => !v)}
          >
            <svg viewBox="0 0 24 24">
              <path d="M21 4H3v2h18V4zM3 20h18v-2H3v2zM4 12l4-4 4 4 4-4 4 4v6H4z" />
            </svg>
            边界 ▾
          </button>
          {boundaryMenuOpen && (
            <div
              className="dropdown-menu open"
              style={{ left: 0, top: "calc(100% + 4px)" }}
            >
              <label className="dropdown-item">
                <input
                  type="checkbox"
                  checked={ui.bndCounty}
                  onChange={(e) => ui.set({ bndCounty: e.target.checked })}
                />{" "}
                县界
              </label>
              <label className="dropdown-item">
                <input
                  type="checkbox"
                  checked={ui.bndTownship}
                  onChange={(e) => ui.set({ bndTownship: e.target.checked })}
                />{" "}
                镇界 / 镇名
              </label>
              <label className="dropdown-item">
                <input
                  type="checkbox"
                  checked={ui.bndVillage}
                  onChange={(e) => ui.set({ bndVillage: e.target.checked })}
                />{" "}
                村界
              </label>
              <label className="dropdown-item">
                <input
                  type="checkbox"
                  checked={ui.bndVillageName}
                  onChange={(e) => ui.set({ bndVillageName: e.target.checked })}
                />{" "}
                村名
              </label>
            </div>
          )}
        </div>

        <button
          className={"tb" + (ui.terrainEnabled ? " on" : "")}
          onClick={() => ui.set({ terrainEnabled: !ui.terrainEnabled })}
        >
          <svg viewBox="0 0 24 24">
            <path d="M14 6l-3.75 5L8 8.5 3 15h18z" />
          </svg>
          {ui.terrainEnabled ? "地形 ✓" : "地形"}
        </button>
      </div>

      <div className="status-summary">
        当前位置: {ui.toast?.text || `全部文物 ${allCount} 处`}
      </div>

      <div className="tb-group" style={{ marginLeft: "auto" }}>
        <button className="tb" onClick={onFullscreen} title="全屏">
          <svg viewBox="0 0 24 24">
            <path d="M5 5h6v2H7v4H5V5zm14 0v6h-2V7h-4V5h6zM5 19v-6h2v4h4v2H5zm14-6v6h-6v-2h4v-4h2z" />
          </svg>
        </button>
        <button className="tb" onClick={onReset} title="重置主视角">
          <svg viewBox="0 0 24 24">
            <path d="M12 2L4 7v6c0 5.55 3.84 10.74 8 12 4.16-1.26 8-6.45 8-12V7l-8-5z" />
          </svg>
          重置
        </button>
      </div>
    </div>
  );
}
