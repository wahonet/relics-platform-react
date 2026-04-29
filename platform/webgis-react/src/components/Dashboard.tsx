import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import { useRelicsStore } from "../stores/relicsStore";
import { useFilterStore } from "../stores/filterStore";
import { DIMS, dimValue, dimValues, buildColorMap, DEF_COLOR } from "../utils/dict";
import type { DimDef } from "../utils/dict";
import type { RelicSummary } from "../types";

const TT = {
  backgroundColor: "rgba(13,17,23,.95)",
  borderColor: "rgba(88,166,255,.3)",
  textStyle: { color: "#e6edf3", fontSize: 11 },
};

function countDim(relics: RelicSummary[], dim: DimDef) {
  const counts: Record<string, number> = {};
  relics.forEach((r) => {
    dimValues(r as unknown as Record<string, unknown>, dim).forEach((v) => {
      counts[v] = (counts[v] || 0) + 1;
    });
  });
  const keys = dim.order
    ? dim.order.filter((k) => counts[k])
    : Object.keys(counts).sort((a, b) => counts[b] - counts[a]);
  return { counts, keys };
}

interface ChartCardProps {
  title: string;
  dimId: string;
  type?: "pie" | "bar" | "vbar";
  relics: RelicSummary[];
  colorMap: Record<string, string>;
  onClickItem?: (val: string) => void;
}

function ChartCard({
  title,
  dimId,
  type = "pie",
  relics,
  colorMap,
  onClickItem,
}: ChartCardProps) {
  const dim = DIMS.find((d) => d.id === dimId)!;
  const { counts, keys } = countDim(relics, dim);
  const data = keys.map((k) => ({
    name: k,
    value: counts[k],
    itemStyle: { color: colorMap[k] || DEF_COLOR },
  }));

  let option: Record<string, unknown> = {};
  if (type === "pie") {
    option = {
      tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)", ...TT },
      series: [
        {
          type: "pie",
          radius: ["28%", "58%"],
          center: ["50%", "52%"],
          data,
          label: { color: "#c9d1d9", fontSize: 10, formatter: "{b}\n{c}" },
          labelLine: { lineStyle: { color: "rgba(255,255,255,.2)" } },
        },
      ],
    };
  } else if (type === "bar") {
    const rev = [...keys].reverse();
    option = {
      tooltip: { trigger: "axis", ...TT },
      grid: { left: 6, right: 36, top: 6, bottom: 6, containLabel: true },
      xAxis: {
        type: "value",
        splitLine: { lineStyle: { color: "rgba(255,255,255,.06)" } },
        axisLabel: { color: "#8b949e", fontSize: 9 },
      },
      yAxis: {
        type: "category",
        data: rev,
        axisLabel: { color: "#c9d1d9", fontSize: 10, width: 90, overflow: "truncate" },
        axisTick: { show: false },
        axisLine: { lineStyle: { color: "rgba(255,255,255,.08)" } },
      },
      series: [
        {
          type: "bar",
          data: rev.map((k) => ({
            value: counts[k],
            itemStyle: { color: colorMap[k] || DEF_COLOR },
          })),
          barWidth: 10,
          itemStyle: { borderRadius: [0, 3, 3, 0] },
          label: {
            show: true,
            position: "right",
            color: "#8b949e",
            fontSize: 9,
            formatter: "{c}",
          },
        },
      ],
    };
  } else {
    option = {
      tooltip: { trigger: "axis", ...TT },
      grid: { left: 6, right: 6, top: 12, bottom: 6, containLabel: true },
      xAxis: {
        type: "category",
        data: keys,
        axisLabel: { color: "#8b949e", fontSize: 9, rotate: 25, interval: 0 },
        axisTick: { show: false },
        axisLine: { lineStyle: { color: "rgba(255,255,255,.08)" } },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: "rgba(255,255,255,.06)" } },
        axisLabel: { color: "#8b949e", fontSize: 9 },
      },
      series: [
        {
          type: "bar",
          data: keys.map((k) => ({
            value: counts[k],
            itemStyle: { color: colorMap[k] || DEF_COLOR },
          })),
          barWidth: 14,
          itemStyle: { borderRadius: [3, 3, 0, 0] },
        },
      ],
    };
  }

  const onEvents: Record<string, (e: { name?: string }) => void> = onClickItem
    ? {
        click: (e: { name?: string }) => {
          if (e?.name) onClickItem(e.name);
        },
      }
    : {};

  return (
    <div className="dash-sec">
      <h4>{title}</h4>
      <ReactECharts
        option={option}
        notMerge
        lazyUpdate
        style={{ width: "100%", height: 220 }}
        onEvents={onEvents}
      />
    </div>
  );
}

export function Dashboard() {
  const allRelics = useRelicsStore((s) => s.all);
  const filter = useFilterStore();
  const setStatFilters = useFilterStore((s) => s.setStatFilters);
  const statFilters = filter.statFilters;
  const toggleStat = (dimId: string, value: string) => {
    const next = { ...statFilters };
    if (next[dimId] === value) delete next[dimId];
    else next[dimId] = value;
    setStatFilters(next);
  };

  const relicsForChart = useMemo(() => {
    const lvDim = DIMS.find((d) => d.id === "heritage_level");
    const twDim = DIMS.find((d) => d.id === "township");
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
      for (const [sfDim, sfVal] of Object.entries(statFilters)) {
        const dim = DIMS.find((d) => d.id === sfDim);
        if (dim) {
          const vals = dimValues(r as unknown as Record<string, unknown>, dim);
          if (!vals.includes(sfVal)) return false;
        }
      }
      return true;
    });
  }, [allRelics, filter, statFilters]);

  const totalRecords = relicsForChart.length;
  const has3d = relicsForChart.filter((r) => r.has_3d).length;

  const colorMaps = useMemo(() => {
    const out: Record<string, Record<string, string>> = {};
    DIMS.forEach((d) => {
      out[d.id] = buildColorMap(allRelics as unknown as Record<string, unknown>[], d);
    });
    return out;
  }, [allRelics]);

  return (
    <div className="dash dock-l">
      <div className="dash-hdr">综合统计</div>
      <div className="dash-cards">
        <div className="dc">
          <div className="n">{totalRecords}</div>
          <div className="l">当前文物总数</div>
        </div>
        <div className="dc y">
          <div className="n">{has3d}</div>
          <div className="l">三维模型</div>
        </div>
      </div>
      <ChartCard title="文物类别" dimId="category_main" type="pie" relics={relicsForChart} colorMap={colorMaps.category_main} onClickItem={(v) => toggleStat("category_main", v)} />
      <ChartCard title="文物级别" dimId="heritage_level" type="bar" relics={relicsForChart} colorMap={colorMaps.heritage_level} onClickItem={(v) => toggleStat("heritage_level", v)} />
      <ChartCard title="年代分布" dimId="era" type="vbar" relics={relicsForChart} colorMap={colorMaps.era} onClickItem={(v) => toggleStat("era", v)} />
      <ChartCard title="乡镇分布" dimId="township" type="bar" relics={relicsForChart} colorMap={colorMaps.township} onClickItem={(v) => toggleStat("township", v)} />
      <ChartCard title="普查类型" dimId="survey_type" type="pie" relics={relicsForChart} colorMap={colorMaps.survey_type} onClickItem={(v) => toggleStat("survey_type", v)} />
      <ChartCard title="保存状态" dimId="condition_level" type="pie" relics={relicsForChart} colorMap={colorMaps.condition_level} onClickItem={(v) => toggleStat("condition_level", v)} />
      <ChartCard title="所有权" dimId="ownership_type" type="pie" relics={relicsForChart} colorMap={colorMaps.ownership_type} onClickItem={(v) => toggleStat("ownership_type", v)} />
      <ChartCard title="所属行业" dimId="industry" type="bar" relics={relicsForChart} colorMap={colorMaps.industry} onClickItem={(v) => toggleStat("industry", v)} />
      <ChartCard title="影响因素" dimId="risk_factors" type="bar" relics={relicsForChart} colorMap={colorMaps.risk_factors} onClickItem={(v) => toggleStat("risk_factors", v)} />
    </div>
  );
}
