import { useEffect, useMemo } from "react";
import { useFilterStore } from "../stores/filterStore";
import { useRelicsStore } from "../stores/relicsStore";
import { useUIStore } from "../stores/uiStore";
import { DIMS, dimValue, buildColorMap } from "../utils/dict";
import { fetchRelicDetail } from "../api/relics";

export function FilterPanel() {
  const open = useUIStore((s) => s.filterPanelOpen);
  const setUI = useUIStore((s) => s.set);
  const filter = useFilterStore();
  const allRelics = useRelicsStore((s) => s.all);

  const lvDim = DIMS.find((d) => d.id === "heritage_level");
  const twDim = DIMS.find((d) => d.id === "township");
  const catDim = DIMS.find((d) => d.id === "category_main")!;

  const towns = useMemo(() => {
    const set = new Set<string>();
    allRelics.forEach((r) => {
      if (r.township)
        set.add(twDim ? dimValue(r as Record<string, unknown>, twDim) : r.township);
    });
    return [...set].sort();
  }, [allRelics, twDim]);

  const levels = useMemo(() => {
    const set = new Set<string>();
    allRelics.forEach((r) => {
      if (r.heritage_level)
        set.add(
          lvDim ? dimValue(r as Record<string, unknown>, lvDim) : r.heritage_level,
        );
    });
    return [...set].sort();
  }, [allRelics, lvDim]);

  const conds = useMemo(() => {
    const set = new Set<string>();
    allRelics.forEach((r) => {
      if (r.condition_level) set.add(r.condition_level);
    });
    return [...set].sort();
  }, [allRelics]);

  const catNames = useMemo(
    () =>
      [...new Set(allRelics.map((r) => r.category_main).filter(Boolean) as string[])].sort(),
    [allRelics],
  );

  const colorMap = useMemo(
    () => buildColorMap(allRelics as unknown as Record<string, unknown>[], catDim),
    [allRelics, catDim],
  );

  // 首次加载完成后,把所有类别默认全选
  useEffect(() => {
    if (catNames.length > 0 && filter.activeCats.size === 0) {
      filter.setActiveCats(new Set(catNames));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [catNames.length]);

  const filteredCount = useMemo(() => {
    return allRelics.filter((r) => {
      if (filter.activeCats.size && r.category_main && !filter.activeCats.has(r.category_main))
        return false;
      const kw = filter.search.trim().toLowerCase();
      if (
        kw &&
        !(r.name || "").toLowerCase().includes(kw) &&
        !(r.archive_code || "").toLowerCase().includes(kw) &&
        !(r.address || "").toLowerCase().includes(kw)
      )
        return false;
      if (filter.township && twDim && dimValue(r as Record<string, unknown>, twDim) !== filter.township)
        return false;
      if (filter.level && lvDim && dimValue(r as Record<string, unknown>, lvDim) !== filter.level)
        return false;
      if (filter.cond && r.condition_level !== filter.cond) return false;
      if (filter.threeD === "1" && !r.has_3d) return false;
      if (filter.threeD === "0" && r.has_3d) return false;
      return true;
    }).length;
  }, [allRelics, filter, twDim, lvDim]);

  const has3dCount = useMemo(
    () => allRelics.filter((r) => r.has_3d).length,
    [allRelics],
  );

  return (
    <div className={"filter-panel" + (open ? " open" : "")}>
      <div className="fp-title">
        筛选与搜索
        <button onClick={() => setUI({ filterPanelOpen: false })}>×</button>
      </div>
      <div className="fp-stat">
        当前 <b>{filteredCount}</b> 处文物，其中 <small>{has3dCount}</small> 处有三维模型
      </div>
      <div className="fp-section">
        <div className="fp-label">关键字搜索</div>
        <input
          className="fp-search"
          placeholder="按名称 / 编号 / 地址搜索..."
          value={filter.search}
          onChange={(e) => filter.setPartial({ search: e.target.value })}
        />
      </div>
      <div className="fp-section">
        <div className="fp-label">文物类别</div>
        <div className="fp-checks">
          {catNames.map((name) => {
            const displayName = name === "近现代重要史迹及代表性建筑" ? "近现代史迹" : name;
            const active = filter.activeCats.has(name);
            return (
              <div
                key={name}
                className={"fp-chk" + (active ? " active" : "")}
                onClick={() => filter.toggleCat(name)}
              >
                <div
                  className="dot"
                  style={{ background: colorMap[displayName] || "#8b949e" }}
                />
                {displayName}
              </div>
            );
          })}
        </div>
      </div>
      <div className="fp-section">
        <div className="fp-label">乡镇</div>
        <select
          className="fp-select"
          value={filter.township}
          onChange={(e) => filter.setPartial({ township: e.target.value })}
        >
          <option value="">全部乡镇</option>
          {towns.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </div>
      <div className="fp-section">
        <div className="fp-label">保护级别</div>
        <select
          className="fp-select"
          value={filter.level}
          onChange={(e) => filter.setPartial({ level: e.target.value })}
        >
          <option value="">全部级别</option>
          {levels.map((l) => (
            <option key={l} value={l}>
              {l}
            </option>
          ))}
        </select>
      </div>
      <div className="fp-section">
        <div className="fp-label">保存现状</div>
        <select
          className="fp-select"
          value={filter.cond}
          onChange={(e) => filter.setPartial({ cond: e.target.value })}
        >
          <option value="">全部现状</option>
          {conds.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </div>
      <div className="fp-section">
        <div className="fp-label">三维模型</div>
        <select
          className="fp-select"
          value={filter.threeD}
          onChange={(e) => filter.setPartial({ threeD: e.target.value as "" | "1" | "0" })}
        >
          <option value="">全部</option>
          <option value="1">仅有三维</option>
          <option value="0">仅无三维</option>
        </select>
      </div>
      <div className="fp-actions">
        <button
          className="fp-btn primary"
          onClick={() => setUI({ filterPanelOpen: false })}
        >
          应用
        </button>
        <button
          className="fp-btn secondary"
          onClick={() => filter.reset(new Set(catNames))}
        >
          重置
        </button>
      </div>
      <div className="fp-section" style={{ borderTop: "1px solid var(--bd)", flex: 1 }}>
        <div className="fp-label">搜索结果（前 50）</div>
        <div>
          {allRelics
            .filter((r) => {
              if (
                filter.activeCats.size &&
                r.category_main &&
                !filter.activeCats.has(r.category_main)
              )
                return false;
              const kw = filter.search.trim().toLowerCase();
              if (
                kw &&
                !(r.name || "").toLowerCase().includes(kw) &&
                !(r.archive_code || "").toLowerCase().includes(kw) &&
                !(r.address || "").toLowerCase().includes(kw)
              )
                return false;
              if (
                filter.township &&
                twDim &&
                dimValue(r as Record<string, unknown>, twDim) !== filter.township
              )
                return false;
              if (
                filter.level &&
                lvDim &&
                dimValue(r as Record<string, unknown>, lvDim) !== filter.level
              )
                return false;
              if (filter.cond && r.condition_level !== filter.cond) return false;
              if (filter.threeD === "1" && !r.has_3d) return false;
              if (filter.threeD === "0" && r.has_3d) return false;
              return true;
            })
            .slice(0, 50)
            .map((r) => (
              <div
                key={r.archive_code}
                className="list-item"
                onClick={async () => {
                  try {
                    const full = await fetchRelicDetail(r.archive_code);
                    setUI({ selectedRelic: full });
                  } catch {
                    setUI({ selectedRelic: r });
                  }
                }}
              >
                <div className="li-name">{r.name}</div>
                <div className="li-meta">
                  <span className="li-cat">{r.category_main || ""}</span>
                  <span className="li-era">{r.era || ""}</span>
                  <span>{r.township || ""}</span>
                </div>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}
