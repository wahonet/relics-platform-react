import * as Cesium from "cesium";

interface BoundaryItem {
  fill: Cesium.Entity;
  line: Cesium.Entity;
  type: string;
}

const COLORS = {
  county: { r: 255, g: 200, b: 50 },
  township: { r: 88, g: 166, b: 255 },
  village: { r: 63, g: 185, b: 80 },
};

function dpDist(p: number[], a: number[], b: number[]): number {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const lenSq = dx * dx + dy * dy;
  if (lenSq === 0) return Math.hypot(p[0] - a[0], p[1] - a[1]);
  const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / lenSq));
  return Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy);
}

function simplifyRing(pts: number[][], eps: number): number[][] {
  if (pts.length <= 4) return pts;
  let maxD = 0;
  let idx = 0;
  for (let i = 1; i < pts.length - 1; i++) {
    const d = dpDist(pts[i], pts[0], pts[pts.length - 1]);
    if (d > maxD) {
      maxD = d;
      idx = i;
    }
  }
  if (maxD > eps) {
    const left = simplifyRing(pts.slice(0, idx + 1), eps);
    const right = simplifyRing(pts.slice(idx), eps);
    return left.slice(0, -1).concat(right);
  }
  return [pts[0], pts[pts.length - 1]];
}

function smoothRing(pts: number[][], iterations: number): number[][] {
  let cur = pts;
  for (let n = 0; n < iterations; n++) {
    const next: number[][] = [cur[0]];
    for (let i = 1; i < cur.length - 1; i++) {
      next.push([
        cur[i - 1][0] * 0.25 + cur[i][0] * 0.5 + cur[i + 1][0] * 0.25,
        cur[i - 1][1] * 0.25 + cur[i][1] * 0.5 + cur[i + 1][1] * 0.25,
      ]);
    }
    next.push(cur[cur.length - 1]);
    cur = next;
  }
  return cur;
}

function prepareRing(ring: number[][], type: string) {
  if (type === "village") return ring;
  const eps = type === "county" ? 0.0001 : 0.00015;
  const iters = type === "county" ? 3 : 2;
  return smoothRing(simplifyRing(ring, eps), iters);
}

function ringCenter(ring: number[][]) {
  const lngs = ring.map((c) => c[0]);
  const lats = ring.map((c) => c[1]);
  return [
    (Math.min(...lngs) + Math.max(...lngs)) / 2,
    (Math.min(...lats) + Math.max(...lats)) / 2,
  ];
}

export class BoundaryLayer {
  private viewer: Cesium.Viewer;
  private layers = {
    county: [] as BoundaryItem[],
    township: [] as BoundaryItem[],
    townLabel: [] as Cesium.Entity[],
    village: [] as BoundaryItem[],
    villageLabel: [] as Cesium.Entity[],
  };
  private villageGeojson: {
    features: {
      properties?: Record<string, string>;
      geometry: { coordinates: number[][][] };
    }[];
  } | null = null;
  public townshipNames: string[] = [];

  constructor(viewer: Cesium.Viewer) {
    this.viewer = viewer;
  }

  private addBoundary(ring: number[][], type: string, name?: string): BoundaryItem {
    const c = COLORS[type as keyof typeof COLORS] || COLORS.county;
    const lineAlpha = type === "county" ? 0.9 : type === "township" ? 0.7 : 0.6;
    const lineW = type === "county" ? 2.5 * 1.3 : 2.5;
    const smoothed = prepareRing(ring, type);
    const positions = smoothed.map((p) => Cesium.Cartesian3.fromDegrees(p[0], p[1]));

    const fillOpts: Cesium.Entity.ConstructorOptions = {
      polygon: {
        hierarchy: new Cesium.PolygonHierarchy(positions),
        material:
          type === "county"
            ? Cesium.Color.TRANSPARENT
            : new Cesium.Color(c.r / 255, c.g / 255, c.b / 255, 0.1),
        height: 0,
      },
    };
    if (name) {
      fillOpts.properties = new Cesium.PropertyBag({
        _boundaryType: type,
        _boundaryName: name,
      });
    }
    const fill = this.viewer.entities.add(fillOpts);
    const closed = [...positions, positions[0]];
    const line = this.viewer.entities.add({
      polyline: {
        positions: closed,
        width: lineW,
        material: new Cesium.Color(c.r / 255, c.g / 255, c.b / 255, lineAlpha),
        clampToGround: true,
      },
    });
    return { fill, line, type };
  }

  private addLabel(lng: number, lat: number, text: string, scale = 0.7, maxDist = 80000) {
    return this.viewer.entities.add({
      position: Cesium.Cartesian3.fromDegrees(lng, lat),
      label: {
        text,
        font: 'bold 18px "Microsoft YaHei", sans-serif',
        fillColor: Cesium.Color.fromCssColorString("rgba(255,200,50,0.95)"),
        outlineColor: Cesium.Color.BLACK,
        outlineWidth: 4,
        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
        heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
        distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, maxDist),
        scale,
      },
    });
  }

  async load() {
    try {
      const [countyRes, townRes, villageRes] = await Promise.all([
        fetch("/boundaries/county.geojson"),
        fetch("/boundaries/townships.geojson"),
        fetch("/boundaries/villages.geojson"),
      ]);
      if (countyRes.ok) {
        const county = await countyRes.json();
        county.features?.forEach(
          (f: { geometry: { coordinates: number[][][] } }) => {
            f.geometry.coordinates.forEach((ring) => {
              this.layers.county.push(this.addBoundary(ring, "county"));
            });
          },
        );
      }
      if (townRes.ok) {
        const towns = await townRes.json();
        const namesSet = new Set<string>();
        towns.features?.forEach(
          (f: {
            properties?: Record<string, string>;
            geometry: { coordinates: number[][][] };
          }) => {
            const name = f.properties?.XZQMC || f.properties?._township_name || "";
            if (name) namesSet.add(name);
            f.geometry.coordinates.forEach((ring) => {
              this.layers.township.push(this.addBoundary(ring, "township", name));
              if (name) {
                const [cx, cy] = ringCenter(ring);
                this.layers.townLabel.push(this.addLabel(cx, cy, name, 0.7, 80000));
              }
            });
          },
        );
        this.townshipNames = [...namesSet].sort();
      }
      if (villageRes.ok) {
        this.villageGeojson = await villageRes.json();
      }
    } catch (e) {
      console.warn("边界加载失败:", e);
    }
  }

  private renderVillages() {
    this.layers.village.forEach((item) => {
      this.viewer.entities.remove(item.fill);
      this.viewer.entities.remove(item.line);
    });
    this.layers.village = [];
    if (!this.villageGeojson) return;
    this.villageGeojson.features.forEach((f) => {
      const name = f.properties?.ZLDWMC || "";
      f.geometry.coordinates.forEach((ring) => {
        this.layers.village.push(this.addBoundary(ring, "village", name));
      });
    });
  }

  private ensureVillageNameLabels() {
    if (this.layers.villageLabel.length > 0) return;
    if (!this.villageGeojson) return;
    this.villageGeojson.features.forEach((f) => {
      const name = f.properties?.ZLDWMC || "";
      if (!name) return;
      const coords = f.geometry.coordinates;
      if (!coords?.length) return;
      const [cx, cy] = ringCenter(coords[0]);
      this.layers.villageLabel.push(this.addLabel(cx, cy, name, 0.6, 30000));
    });
  }

  setVisibility(opts: {
    county: boolean;
    township: boolean;
    village: boolean;
    villageName: boolean;
  }) {
    this.layers.county.forEach((it) => {
      it.fill.show = opts.county;
      it.line.show = opts.county;
    });
    this.layers.township.forEach((it) => {
      it.fill.show = opts.township;
      it.line.show = opts.township;
    });
    this.layers.townLabel.forEach((e) => (e.show = opts.township));

    if (opts.village && this.layers.village.length === 0) this.renderVillages();
    this.layers.village.forEach((it) => {
      it.fill.show = opts.village;
      it.line.show = opts.village;
    });
    if (opts.villageName) this.ensureVillageNameLabels();
    this.layers.villageLabel.forEach((e) => (e.show = opts.villageName));
    this.viewer.scene.requestRender();
  }
}
