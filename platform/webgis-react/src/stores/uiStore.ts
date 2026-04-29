import { create } from "zustand";
import type { BaseLayerType, RelicSummary } from "../types";

interface UIState {
  filterPanelOpen: boolean;
  routePanelOpen: boolean;
  chatPanelOpen: boolean;
  settingsPanelOpen: boolean;
  helpPanelOpen: boolean;
  tileDownloadOpen: boolean;
  worklogOpen: boolean;

  baseLayer: BaseLayerType;
  baseLayerAlpha: number;
  terrainEnabled: boolean;

  bndCounty: boolean;
  bndTownship: boolean;
  bndVillage: boolean;
  bndVillageName: boolean;

  symbolMode: boolean;
  hdMode: boolean;
  hideRelicPoints: boolean;
  uiSize: "sm" | "md" | "lg";
  theme: "blue" | "purple" | "gold" | "pink";
  activeGroup: string;

  selectedRelic: RelicSummary | null;
  worklogDate: string | null;

  toast: { id: number; text: string } | null;

  set: (patch: Partial<Omit<UIState, "set" | "showToast">>) => void;
  showToast: (text: string) => void;
}

let toastSeq = 0;
let toastT: ReturnType<typeof setTimeout> | null = null;

export const useUIStore = create<UIState>((set, get) => ({
  filterPanelOpen: false,
  routePanelOpen: false,
  chatPanelOpen: false,
  settingsPanelOpen: false,
  helpPanelOpen: false,
  tileDownloadOpen: false,
  worklogOpen: false,

  baseLayer: "arcgis_sat",
  baseLayerAlpha: 90,
  terrainEnabled: false,

  bndCounty: true,
  bndTownship: true,
  bndVillage: false,
  bndVillageName: false,

  symbolMode: false,
  hdMode: localStorage.getItem("hdMode") === "1",
  hideRelicPoints: false,
  uiSize: "md",
  theme: "blue",
  activeGroup: "category_main",

  selectedRelic: null,
  worklogDate: null,

  toast: null,

  set(patch) {
    set(patch);
  },
  showToast(text) {
    if (toastT) clearTimeout(toastT);
    set({ toast: { id: ++toastSeq, text } });
    toastT = setTimeout(() => {
      const cur = get().toast;
      if (cur && cur.text === text) set({ toast: null });
    }, 2200);
  },
}));
