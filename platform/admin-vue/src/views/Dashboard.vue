<template>
  <div class="page-container dashboard">
    <div class="page-title">
      数据概览
      <span class="sub">
        <template v-if="stats?.last_updated">
          · 数据最后更新 {{ fmtTs(stats.last_updated) }}
        </template>
      </span>
      <div class="top-actions">
        <el-button plain :icon="Refresh" :loading="loading" @click="reload">
          刷新
        </el-button>
      </div>
    </div>

    <!-- 核心指标卡片 -->
    <el-row :gutter="12" class="stat-row">
      <el-col
        v-for="c in cards"
        :key="c.key"
        :xs="12"
        :sm="8"
        :md="4"
      >
        <div class="stat-card" @click="c.to && $router.push(c.to)">
          <div class="stat-icon" :style="{ color: c.color }">
            <el-icon :size="20"><component :is="c.icon" /></el-icon>
          </div>
          <div class="stat-main">
            <div class="stat-label">{{ c.label }}</div>
            <div class="stat-value" :style="{ color: c.color }">{{ c.value }}</div>
            <!-- total 卡片：副文案拆成 2 个链接；其他卡片：纯文本 -->
            <div v-if="c.key === 'total'" class="stat-sub">
              <a class="sub-link" @click.stop="$router.push('/relics?status=0')">
                草稿 {{ stats?.totals?.drafts ?? 0 }}
              </a>
              <span class="sub-sep">·</span>
              <a class="sub-link danger" @click.stop="$router.push('/relics?status=-1')">
                <el-icon class="sub-ic"><Delete /></el-icon>
                回收站 {{ stats?.totals?.deleted ?? 0 }}
              </a>
            </div>
            <div v-else class="stat-sub">{{ c.sub }}</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 第一行图表：类别 + 级别 -->
    <el-row :gutter="12" class="chart-row">
      <el-col :xs="24" :md="12">
        <div class="chart-card">
          <div class="chart-head">
            <span>文物大类分布</span>
            <span class="chart-sub">GB/T 15420 国标六大类</span>
          </div>
          <div ref="donutCatRef" class="chart-body chart-h300" />
        </div>
      </el-col>
      <el-col :xs="24" :md="12">
        <div class="chart-card">
          <div class="chart-head">
            <span>保护级别分布</span>
            <span class="chart-sub">国保 / 省保 / 市保 / 县保 / 未定级</span>
          </div>
          <div ref="barRankRef" class="chart-body chart-h300" />
        </div>
      </el-col>
    </el-row>

    <!-- 第二行：乡镇 Top15 -->
    <el-row :gutter="12" class="chart-row">
      <el-col :span="24">
        <div class="chart-card">
          <div class="chart-head">
            <span>乡镇文物数 Top 15</span>
            <span class="chart-sub">点击条目跳转列表筛选</span>
          </div>
          <div ref="barTownshipRef" class="chart-body chart-h360" />
        </div>
      </el-col>
    </el-row>

    <!-- 管线健康：六步状态 + 上次运行时间 + 失败高亮 -->
    <el-row :gutter="12" class="chart-row">
      <el-col :span="24">
        <div class="chart-card pipeline-card">
          <div class="chart-head">
            <span>
              数据管线健康
              <el-tag
                v-if="pipelineHasError"
                size="small"
                type="danger"
                effect="dark"
                class="head-tag"
              >
                有失败
              </el-tag>
              <el-tag
                v-else-if="pipelineAnyRun"
                size="small"
                type="success"
                effect="dark"
                class="head-tag"
              >
                正常
              </el-tag>
            </span>
            <span class="chart-sub">最近一次各 step 运行状态 · 点击进入管线页</span>
            <router-link to="/pipeline" class="chart-link">去管线 →</router-link>
          </div>
          <div v-loading="pipelineLoading" class="pipeline-grid">
            <div
              v-for="s in pipelineSteps"
              :key="s.id"
              class="pipe-step"
              :class="pipeStepClass(s)"
              @click="goPipeline(s.id)"
            >
              <div class="pipe-step-head">
                <span class="pipe-ico">{{ s.icon }}</span>
                <span class="pipe-name">{{ s.name }}</span>
                <el-tag
                  size="small"
                  :type="pipeTagType(s)"
                  effect="plain"
                  class="pipe-status-tag"
                >
                  {{ pipeStatusText(s) }}
                </el-tag>
              </div>
              <el-progress
                :percentage="Math.round(s.progress)"
                :status="pipeProgressStatus(s)"
                :stroke-width="6"
                :show-text="false"
                class="pipe-progress"
              />
              <div class="pipe-meta">
                <span class="pipe-flow">{{ s.flow }}</span>
                <span class="pipe-pending" :class="{ 'has-pending': s.pending > 0 }">
                  待处理 {{ s.pending }}
                </span>
              </div>
              <div class="pipe-last">
                <template v-if="s.last_run?.started">
                  <el-icon class="pipe-last-ic"><Clock /></el-icon>
                  <span class="mono">{{ relativeDate(s.last_run.started) }}</span>
                </template>
                <template v-else-if="s.artifact_mtime">
                  <el-icon class="pipe-last-ic"><Document /></el-icon>
                  <span class="mono">{{ relativeDate(s.artifact_mtime) }}</span>
                </template>
                <template v-else>
                  <span class="muted">未运行</span>
                </template>
              </div>
            </div>
            <div v-if="!pipelineSteps.length && !pipelineLoading" class="pipeline-empty">
              管线状态不可用
            </div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 瓦片缓存：离线地图下载量 + 最近下载记录 -->
    <el-row :gutter="12" class="chart-row">
      <el-col :span="24">
        <div class="chart-card tile-card" v-loading="tilesLoading">
          <div class="chart-head">
            <span>
              离线瓦片缓存
              <el-tag
                v-if="tilesSummary && tilesSummary.totals.count > 0"
                size="small"
                type="success"
                effect="dark"
                class="head-tag"
              >
                {{ tilesSummary.totals.count }} 张 · {{ fmtMB(tilesSummary.totals.bytes) }}
              </el-tag>
              <el-tag
                v-else-if="tilesSummary"
                size="small"
                type="info"
                effect="dark"
                class="head-tag"
              >
                无缓存
              </el-tag>
            </span>
            <span class="chart-sub">
              在首页地图的"离线瓦片下载"面板里按县域或框选下载；此处展示全局缓存与下载历史
            </span>
            <a
              href="/#download"
              target="_blank"
              class="chart-link"
              @click.prevent="openMapDownload"
            >去地图下载 →</a>
          </div>

          <div class="tile-body">
            <!-- 左：各 provider 缓存体量 -->
            <div class="tile-col">
              <div class="tile-col-title">
                各瓦片源
                <span class="tile-sub">
                  最近一次：{{ relativeFromEpoch(tilesSummary?.last_finished_at) }}
                </span>
              </div>
              <div v-if="tilesProviderList.length" class="tile-prov-list">
                <div
                  v-for="p in tilesProviderList"
                  :key="p.key"
                  class="tile-prov-row"
                >
                  <span class="tp-name">{{ providerLabel(p.key) }}</span>
                  <span class="tp-spacer"></span>
                  <span class="tp-count">{{ p.count }} 张</span>
                  <span class="tp-sep">·</span>
                  <span class="tp-bytes">{{ fmtMB(p.bytes) }}</span>
                </div>
              </div>
              <div v-else class="tile-empty">尚未下载任何离线瓦片</div>
              <div class="tile-path">
                <el-icon><FolderOpened /></el-icon>
                <code>{{ tilesSummary?.cache_dir || '—' }}</code>
              </div>
            </div>

            <!-- 右：最近下载历史 -->
            <div class="tile-col">
              <div class="tile-col-title">
                最近下载记录
                <span class="tile-sub">{{ tilesSummary?.recent?.length || 0 }} 条</span>
              </div>
              <div v-if="tilesSummary?.recent?.length" class="tile-hist-list">
                <div
                  v-for="h in tilesSummary.recent"
                  :key="h.id"
                  class="tile-hist-row"
                  :class="{ err: h.status === 'error' }"
                >
                  <div class="th-head">
                    <span class="th-label">
                      <el-icon class="th-ic"><MapLocation /></el-icon>
                      {{ h.label || '手动框选范围' }}
                    </span>
                    <el-tag
                      size="small"
                      :type="h.status === 'done' ? 'success' : (h.status === 'error' ? 'danger' : 'primary')"
                      effect="plain"
                      class="th-tag"
                    >
                      {{ h.status === 'done' ? '完成' : (h.status === 'error' ? '失败' : '进行中') }}
                    </el-tag>
                  </div>
                  <div class="th-meta">
                    <span>Z{{ h.zooms.join(' · Z') }}</span>
                    <span class="dot-sep">·</span>
                    <span>{{ (h.providers || []).map(providerLabel).join(' / ') }}</span>
                  </div>
                  <div class="th-stats">
                    <span class="s-item">
                      新增 <b class="ok">{{ h.downloaded }}</b> 张
                    </span>
                    <span class="s-item">
                      命中 <b class="muted">{{ h.skipped }}</b>
                    </span>
                    <span v-if="h.failed" class="s-item">
                      失败 <b class="err">{{ h.failed }}</b>
                    </span>
                    <span class="s-item">{{ fmtMB(h.bytes) }}</span>
                    <span class="s-time">{{ relativeFromEpoch(h.finished_at || h.started_at) }}</span>
                  </div>
                </div>
              </div>
              <div v-else class="tile-empty">暂无下载历史</div>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 第三行：14 天审计趋势 + 最近活动 -->
    <el-row :gutter="12" class="chart-row">
      <el-col :xs="24" :lg="14">
        <div class="chart-card">
          <div class="chart-head">
            <span>最近 14 天变更趋势</span>
            <span class="chart-sub">基于审计日志聚合</span>
          </div>
          <div ref="lineAuditRef" class="chart-body chart-h280" />
        </div>
      </el-col>
      <el-col :xs="24" :lg="10">
        <div class="chart-card activity-card">
          <div class="chart-head">
            <span>最近活动</span>
            <router-link to="/audit" class="chart-link">查看全部 →</router-link>
          </div>
          <div class="activity-list">
            <div
              v-for="r in stats?.audit_recent || []"
              :key="r.id"
              class="activity-item"
              @click="goAudit(r.relic_code)"
            >
              <div class="act-left">
                <el-tag
                  size="small"
                  :type="actionType(r.action)"
                  effect="dark"
                  class="act-tag"
                >
                  {{ actionLabel(r.action) }}
                </el-tag>
                <span class="act-name">
                  {{ r.relic_name || r.relic_code || '—' }}
                </span>
              </div>
              <div class="act-right">
                <span class="act-actor">{{ r.actor || 'system' }}</span>
                <span class="act-ts">{{ relativeTs(r.ts) }}</span>
              </div>
            </div>
            <div v-if="!stats?.audit_recent?.length" class="activity-empty">
              暂无审计记录
            </div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 年代分布 + 来源 -->
    <el-row :gutter="12" class="chart-row">
      <el-col :xs="24" :md="14">
        <div class="chart-card">
          <div class="chart-head">
            <span>年代分布 Top 8</span>
            <span class="chart-sub">基于 era_stats 归并字段</span>
          </div>
          <div ref="barEraRef" class="chart-body chart-h260" />
        </div>
      </el-col>
      <el-col :xs="24" :md="10">
        <div class="chart-card">
          <div class="chart-head">
            <span>普查来源构成</span>
            <span class="chart-sub">三普在册 / 县级以上 / 四普新增</span>
          </div>
          <div ref="pieSearchRef" class="chart-body chart-h260" />
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import * as echarts from 'echarts';
import type { EChartsOption } from 'echarts';
import {
  Clock,
  Collection,
  Delete,
  Document,
  DocumentCopy,
  FolderOpened,
  MapLocation,
  PictureFilled,
  Refresh,
  Star,
  VideoCamera,
} from '@element-plus/icons-vue';
import { adminApi, type PipelineStep, type StatsOverview, type TilesSummary } from '@/api/admin';

const router = useRouter();

const loading = ref(false);
const stats = ref<StatsOverview | null>(null);
const pipelineSteps = ref<PipelineStep[]>([]);
const pipelineLoading = ref(false);
const tilesSummary = ref<TilesSummary | null>(null);
const tilesLoading = ref(false);

// ── 图表 refs ────────────────────────────────
const donutCatRef = ref<HTMLDivElement>();
const barRankRef = ref<HTMLDivElement>();
const barTownshipRef = ref<HTMLDivElement>();
const lineAuditRef = ref<HTMLDivElement>();
const barEraRef = ref<HTMLDivElement>();
const pieSearchRef = ref<HTMLDivElement>();

const charts: echarts.ECharts[] = [];

// ── 主题（深色，对齐主图）────────────────────
const TEXT = '#c9d1d9';
const TEXT_DIM = '#8b949e';
const LINE = 'rgba(88, 166, 255, 0.15)';
const PALETTE = ['#58a6ff', '#3fb950', '#d29922', '#bc8cff', '#f85149', '#79c0ff', '#ffd700'];

function baseOpts(): Partial<EChartsOption> {
  return {
    backgroundColor: 'transparent',
    color: PALETTE,
    textStyle: { color: TEXT, fontFamily: 'inherit' },
    tooltip: {
      backgroundColor: 'rgba(22, 27, 34, 0.96)',
      borderColor: 'rgba(88, 166, 255, 0.3)',
      textStyle: { color: TEXT },
    },
    grid: { left: 40, right: 20, top: 30, bottom: 30, containLabel: true },
  };
}

// ── 核心指标 ─────────────────────────────────
const cards = computed(() => {
  const t = stats.value?.totals;
  const ranks = stats.value?.by_rank || [];
  const key1 = ranks.find((r) => r.code === '1')?.count || 0;
  const key2 = ranks.find((r) => r.code === '2')?.count || 0;
  const total = t?.total || 0;
  const photoRate = total > 0 ? Math.round(((t?.has_photo || 0) / total) * 100) : 0;

  return [
    {
      key: 'total', label: '文物总数', value: total,
      sub: t ? `草稿 ${t.drafts} · 已删 ${t.deleted}` : '—',
      icon: Collection, color: '#58a6ff', to: '/relics',
    },
    {
      key: 'topLv', label: '国 / 省级', value: key1 + key2,
      sub: `国保 ${key1} · 省保 ${key2}`,
      icon: Star, color: '#ffd700', to: '/relics?rank=1,2',
    },
    {
      key: '3d', label: '3D 模型', value: t?.has_3d ?? 0,
      sub: total > 0 ? `${pct(t?.has_3d, total)}% 覆盖` : '—',
      icon: VideoCamera, color: '#bc8cff', to: '',
    },
    {
      key: 'photo', label: '照片覆盖', value: `${photoRate}%`,
      sub: t ? `${t.has_photo} / ${total}` : '—',
      icon: PictureFilled, color: '#3fb950', to: '',
    },
    {
      key: 'pdf', label: '档案 PDF', value: t?.has_pdf ?? 0,
      sub: total > 0 ? `${pct(t?.has_pdf, total)}% 覆盖` : '—',
      icon: DocumentCopy, color: '#d29922', to: '',
    },
    {
      key: 'poly', label: '已描边界', value: t?.has_boundary ?? 0,
      sub: total > 0 ? `${pct(t?.has_boundary, total)}% 覆盖` : '—',
      icon: MapLocation, color: '#f85149', to: '',
    },
  ];
});

function pct(n: number | undefined, total: number): number {
  if (!n || !total) return 0;
  return Math.round((n / total) * 100);
}

// ── 加载 + 渲染 ─────────────────────────────
async function reload() {
  loading.value = true;
  pipelineLoading.value = true;
  tilesLoading.value = true;
  try {
    // 三处数据并行拉：stats / pipeline / tiles；图表等 stats 到再画
    const [s] = await Promise.all([
      adminApi.statsOverview().catch(() => null),
      adminApi.pipeline()
        .then((r) => { pipelineSteps.value = r.steps || []; })
        .catch(() => { pipelineSteps.value = []; })
        .finally(() => { pipelineLoading.value = false; }),
      adminApi.tilesSummary(10)
        .then((r) => { tilesSummary.value = r; })
        .catch(() => { tilesSummary.value = null; })
        .finally(() => { tilesLoading.value = false; }),
    ]);
    stats.value = s;
    await nextTick();
    renderCharts();
  } finally {
    loading.value = false;
  }
}

// ── 瓦片缓存卡片:小工具 ──────────────────────
function fmtMB(bytes: number | undefined): string {
  if (!bytes) return '0 MB';
  const mb = bytes / 1024 / 1024;
  if (mb >= 1024) return (mb / 1024).toFixed(2) + ' GB';
  if (mb >= 100) return mb.toFixed(0) + ' MB';
  if (mb >= 10) return mb.toFixed(1) + ' MB';
  return mb.toFixed(2) + ' MB';
}
function providerLabel(p: string): string {
  const m: Record<string, string> = {
    arcgis_sat: '卫星 · ArcGIS',
    osm: '矢量 · OSM',
    gaode_sat: '卫星 · 高德',
    gaode_vec: '矢量 · 高德',
    gaode_anno: '注记 · 高德',
  };
  return m[p] || p;
}
function relativeFromEpoch(sec: number | null | undefined): string {
  if (!sec) return '—';
  const diff = (Date.now() / 1000) - sec;
  if (diff < 60) return '刚刚';
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} 天前`;
  const d = new Date(sec * 1000);
  return `${d.getMonth() + 1}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}
const tilesProviderList = computed(() => {
  const p = tilesSummary.value?.providers || {};
  return Object.keys(p).sort().map((k) => ({ key: k, ...p[k] }));
});

function openMapDownload() {
  // 地图首页装有全局 JS 函数 toggleDownloadPanel(),开新页到 / 即可
  window.open('/', '_blank');
}

// ── 管线健康展示 ────────────────────────────
const pipelineHasError = computed(() =>
  pipelineSteps.value.some((s) => s.last_run?.status === 'error'),
);
const pipelineAnyRun = computed(() =>
  pipelineSteps.value.some((s) => (s.progress ?? 0) > 0),
);

function pipeStatusText(s: PipelineStep): string {
  if (s.last_run?.status === 'running') return '运行中';
  if (s.last_run?.status === 'error') return '失败';
  if (s.pending > 0) return '待处理';
  if (s.progress >= 99.5) return '完成';
  if (s.progress > 0) return '进行中';
  return '未跑';
}
function pipeTagType(s: PipelineStep): 'success' | 'warning' | 'danger' | 'info' | 'primary' {
  if (s.last_run?.status === 'running') return 'primary';
  if (s.last_run?.status === 'error') return 'danger';
  if (s.progress >= 99.5) return 'success';
  if (s.pending > 0) return 'warning';
  return 'info';
}
function pipeProgressStatus(s: PipelineStep): '' | 'success' | 'exception' | 'warning' {
  if (s.last_run?.status === 'error') return 'exception';
  if (s.progress >= 99.5) return 'success';
  if (s.pending > 0) return 'warning';
  return '';
}
function pipeStepClass(s: PipelineStep): Record<string, boolean> {
  return {
    'step-error': s.last_run?.status === 'error',
    'step-running': s.last_run?.status === 'running',
    'step-done': s.progress >= 99.5 && s.last_run?.status !== 'error',
    'step-pending': s.pending > 0 && s.last_run?.status !== 'error',
  };
}
function relativeDate(s: string): string {
  if (!s) return '—';
  const t = new Date(s.replace(' ', 'T')).getTime();
  if (isNaN(t)) return s;
  const now = Date.now();
  const diff = (now - t) / 1000;
  if (diff < 60) return '刚刚';
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} 天前`;
  return s.slice(5, 16);
}
function goPipeline(stepId: string) {
  router.push({ path: '/pipeline', query: { step: stepId } });
}

function renderCharts() {
  if (!stats.value) return;
  renderDonutCategory();
  renderBarRank();
  renderBarTownship();
  renderLineAudit();
  renderBarEra();
  renderPieSearch();
}

function mountChart(el: HTMLDivElement | undefined, opt: EChartsOption): echarts.ECharts | null {
  if (!el) return null;
  // 复用已有实例，改切数据时直接 setOption 不重建
  let inst = echarts.getInstanceByDom(el);
  if (!inst) {
    inst = echarts.init(el);
    charts.push(inst);
  }
  inst.setOption(opt, true);
  return inst;
}

// 1. 类别环形图
function renderDonutCategory() {
  const data = (stats.value?.by_category || [])
    .filter((d) => d.count > 0)
    .map((d) => ({ name: d.label, value: d.count, code: d.code }));

  const inst = mountChart(donutCatRef.value, {
    ...baseOpts(),
    tooltip: { ...baseOpts().tooltip, trigger: 'item', formatter: '{b}<br/>{c} 条 ({d}%)' },
    legend: {
      orient: 'vertical', right: 10, top: 'middle',
      textStyle: { color: TEXT_DIM, fontSize: 12 },
      itemWidth: 10, itemHeight: 10,
    },
    series: [
      {
        type: 'pie', radius: ['45%', '72%'], center: ['35%', '50%'],
        avoidLabelOverlap: true, minAngle: 2,
        itemStyle: { borderColor: '#0d1117', borderWidth: 2 },
        label: { show: false },
        emphasis: { label: { show: true, formatter: '{b}\n{c}', fontSize: 13, color: TEXT } },
        data,
      },
    ],
  });

  inst?.off('click');
  inst?.on('click', (p: any) => {
    if (p?.data?.code) router.push({ path: '/relics', query: { category: p.data.code } });
  });
}

// 2. 保护级别柱状
function renderBarRank() {
  const rows = stats.value?.by_rank || [];
  const SHORT: Record<string, string> = { '1': '国保', '2': '省保', '3': '市保', '4': '县保', '5': '未定级' };
  const RANK_COLOR: Record<string, string> = {
    '1': '#f85149', '2': '#d29922', '3': '#58a6ff', '4': '#3fb950', '5': '#8b949e',
  };

  const inst = mountChart(barRankRef.value, {
    ...baseOpts(),
    tooltip: { ...baseOpts().tooltip, trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: {
      type: 'category',
      data: rows.map((r) => SHORT[r.code] || r.label),
      axisLabel: { color: TEXT_DIM },
      axisLine: { lineStyle: { color: LINE } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: TEXT_DIM },
      splitLine: { lineStyle: { color: LINE } },
    },
    series: [
      {
        type: 'bar', barMaxWidth: 46,
        data: rows.map((r) => ({
          value: r.count, name: SHORT[r.code] || r.label, code: r.code,
          itemStyle: { color: RANK_COLOR[r.code] || '#58a6ff', borderRadius: [4, 4, 0, 0] },
        })),
        label: { show: true, position: 'top', color: TEXT, fontSize: 12 },
      },
    ],
  });

  inst?.off('click');
  inst?.on('click', (p: any) => {
    if (p?.data?.code) router.push({ path: '/relics', query: { rank: p.data.code } });
  });
}

// 3. 乡镇 Top15 横向条形
function renderBarTownship() {
  const rows = [...(stats.value?.by_township_top || [])].reverse();

  const inst = mountChart(barTownshipRef.value, {
    ...baseOpts(),
    grid: { left: 110, right: 30, top: 10, bottom: 20, containLabel: false },
    tooltip: { ...baseOpts().tooltip, trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: {
      type: 'value',
      axisLabel: { color: TEXT_DIM },
      splitLine: { lineStyle: { color: LINE } },
    },
    yAxis: {
      type: 'category',
      data: rows.map((r) => r.name),
      axisLabel: { color: TEXT_DIM, fontSize: 12 },
      axisLine: { lineStyle: { color: LINE } },
    },
    series: [
      {
        type: 'bar', barMaxWidth: 18,
        data: rows.map((r) => ({
          value: r.count, name: r.name,
          itemStyle: {
            color: {
              type: 'linear' as const, x: 0, y: 0, x2: 1, y2: 0,
              colorStops: [{ offset: 0, color: '#1f6feb' }, { offset: 1, color: '#58a6ff' }],
            },
            borderRadius: [0, 4, 4, 0],
          },
        })),
        label: { show: true, position: 'right', color: TEXT, fontSize: 11 },
      },
    ],
  });

  inst?.off('click');
  inst?.on('click', (p: any) => {
    if (p?.data?.name) router.push({ path: '/relics', query: { township: p.data.name } });
  });
}

// 4. 14 天审计折线
function renderLineAudit() {
  const a = stats.value?.audit_14days;
  if (!a) return;
  mountChart(lineAuditRef.value, {
    ...baseOpts(),
    tooltip: { ...baseOpts().tooltip, trigger: 'axis' },
    legend: { top: 0, textStyle: { color: TEXT_DIM }, icon: 'roundRect' },
    grid: { left: 30, right: 20, top: 40, bottom: 30, containLabel: true },
    xAxis: {
      type: 'category', data: a.days.map(shortDay), boundaryGap: false,
      axisLabel: { color: TEXT_DIM, fontSize: 11 },
      axisLine: { lineStyle: { color: LINE } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: TEXT_DIM },
      splitLine: { lineStyle: { color: LINE } },
    },
    series: [
      mkLine('新建', a.create, '#3fb950'),
      mkLine('更新', a.update, '#d29922'),
      mkLine('删除', a.delete, '#f85149'),
    ],
  });
}

function mkLine(name: string, data: number[], color: string) {
  return {
    name,
    type: 'line' as const,
    data,
    smooth: true,
    symbol: 'circle',
    symbolSize: 6,
    lineStyle: { color, width: 2 },
    itemStyle: { color },
    areaStyle: {
      color: {
        type: 'linear' as const,
        x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [
          { offset: 0, color: color + '55' },
          { offset: 1, color: color + '00' },
        ],
      },
    },
  };
}

// 5. 年代 Top8
function renderBarEra() {
  const rows = stats.value?.by_era_stats_top || [];
  mountChart(barEraRef.value, {
    ...baseOpts(),
    tooltip: { ...baseOpts().tooltip, trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: {
      type: 'category', data: rows.map((r) => r.name),
      axisLabel: { color: TEXT_DIM, interval: 0, rotate: rows.length > 5 ? 20 : 0 },
      axisLine: { lineStyle: { color: LINE } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: TEXT_DIM },
      splitLine: { lineStyle: { color: LINE } },
    },
    series: [
      {
        type: 'bar', barMaxWidth: 36,
        data: rows.map((r) => r.count),
        itemStyle: {
          color: {
            type: 'linear' as const, x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [{ offset: 0, color: '#bc8cff' }, { offset: 1, color: '#58a6ff' }],
          },
          borderRadius: [4, 4, 0, 0],
        },
        label: { show: true, position: 'top', color: TEXT, fontSize: 11 },
      },
    ],
  });
}

// 6. 来源饼图
function renderPieSearch() {
  const rows = (stats.value?.by_search_type || []).filter((r) => r.count > 0);
  mountChart(pieSearchRef.value, {
    ...baseOpts(),
    tooltip: { ...baseOpts().tooltip, trigger: 'item', formatter: '{b}<br/>{c} 条 ({d}%)' },
    legend: {
      orient: 'vertical', right: 10, top: 'middle',
      textStyle: { color: TEXT_DIM, fontSize: 12 },
      itemWidth: 10, itemHeight: 10,
    },
    series: [
      {
        type: 'pie', radius: ['35%', '65%'], center: ['35%', '50%'],
        avoidLabelOverlap: true, minAngle: 3,
        itemStyle: { borderColor: '#0d1117', borderWidth: 2 },
        label: { show: false },
        emphasis: { label: { show: true, formatter: '{b}\n{c}', fontSize: 13, color: TEXT } },
        data: rows.map((r) => ({ name: r.label, value: r.count })),
      },
    ],
  });
}

// ── 最近活动格式化 ─────────────────────────
function shortDay(d: string): string {
  // '2026-04-20' → '04-20'
  return d.length >= 10 ? d.slice(5) : d;
}
function fmtTs(ts: number): string {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleString('zh-CN', { hour12: false });
}
function relativeTs(ts: number): string {
  if (!ts) return '';
  const now = Date.now() / 1000;
  const diff = now - ts;
  if (diff < 60) return '刚刚';
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} 天前`;
  return new Date(ts * 1000).toLocaleDateString('zh-CN');
}
function actionLabel(a: string): string {
  return { create: '新建', update: '更新', delete: '删除' }[a] || a;
}
function actionType(a: string): 'success' | 'warning' | 'danger' | 'info' {
  return ({ create: 'success', update: 'warning', delete: 'danger' } as const)[a] || 'info';
}
function goAudit(code: string) {
  router.push({ path: '/audit', query: code ? { code } : {} });
}

// ── resize observer ─────────────────────────
let ro: ResizeObserver | null = null;
function setupResize() {
  ro = new ResizeObserver(() => {
    for (const c of charts) c.resize();
  });
  const root = donutCatRef.value?.parentElement?.parentElement?.parentElement;
  if (root) ro.observe(root);
  window.addEventListener('resize', onWinResize);
}
function onWinResize() {
  for (const c of charts) c.resize();
}

onMounted(async () => {
  await reload();
  setupResize();
});
onBeforeUnmount(() => {
  ro?.disconnect();
  window.removeEventListener('resize', onWinResize);
  for (const c of charts) c.dispose();
  charts.length = 0;
});
</script>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.top-actions { margin-left: auto; }

/* 指标卡 */
.stat-row { margin-bottom: 4px; }
.stat-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  background: linear-gradient(135deg, var(--bg2), var(--bg3));
  border: 1px solid var(--bd);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
  height: 100%;
}
.stat-card:hover {
  border-color: var(--bd-a);
  transform: translateY(-1px);
  box-shadow: 0 2px 10px rgba(88, 166, 255, 0.12);
}
.stat-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: rgba(88, 166, 255, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.stat-main {
  flex: 1;
  min-width: 0;
}
.stat-label {
  font-size: 12px;
  color: var(--t2);
  margin-bottom: 2px;
}
.stat-value {
  font-size: 24px;
  font-weight: 700;
  line-height: 1.2;
  font-family: var(--el-font-family-mono, ui-monospace, Menlo, Consolas, monospace);
}
.stat-sub {
  font-size: 11px;
  color: var(--t2);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sub-link {
  color: var(--t2);
  cursor: pointer;
  border-bottom: 1px dashed transparent;
  transition: all 0.15s;
  display: inline-flex;
  align-items: center;
  gap: 2px;
}
.sub-link:hover {
  color: var(--accent);
  border-bottom-color: var(--accent);
}
.sub-link.danger:hover {
  color: #f85149;
  border-bottom-color: #f85149;
}
.sub-link .sub-ic {
  font-size: 11px;
  vertical-align: -1px;
}
.sub-sep {
  margin: 0 4px;
  color: var(--t3);
}

/* 图表卡 */
.chart-row { margin-bottom: 0; }
.chart-card {
  background: var(--bg2);
  border: 1px solid var(--bd);
  border-radius: 10px;
  padding: 14px 16px;
  margin-bottom: 12px;
  height: 100%;
  box-sizing: border-box;
}
.chart-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 8px;
}
.chart-head > span:first-child {
  font-size: 14px;
  font-weight: 600;
  color: var(--t1);
}
.chart-sub {
  font-size: 12px;
  color: var(--t2);
}
.chart-link {
  margin-left: auto;
  font-size: 12px;
  color: var(--accent);
}
.chart-body { width: 100%; }
.chart-h300 { height: 300px; }

/* 管线健康卡 */
.pipeline-card .head-tag { margin-left: 8px; }
.pipeline-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 10px;
  min-height: 120px;
}
.pipe-step {
  padding: 10px 12px;
  background: var(--bg3);
  border: 1px solid var(--bd);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.pipe-step:hover {
  border-color: var(--bd-a);
  transform: translateY(-1px);
}
.pipe-step.step-error {
  border-color: rgba(248, 81, 73, 0.5);
  background: linear-gradient(135deg, rgba(248, 81, 73, 0.08), var(--bg3));
}
.pipe-step.step-running {
  border-color: rgba(88, 166, 255, 0.5);
}
.pipe-step.step-done { border-color: rgba(63, 185, 80, 0.3); }
.pipe-step.step-pending { border-color: rgba(210, 153, 34, 0.3); }
.pipe-step-head {
  display: flex;
  align-items: center;
  gap: 6px;
}
.pipe-ico { font-size: 16px; flex-shrink: 0; }
.pipe-name {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  color: var(--t1);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pipe-status-tag { flex-shrink: 0; }
.pipe-progress :deep(.el-progress-bar__outer) {
  background: rgba(88, 166, 255, 0.1);
}
.pipe-meta {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--t2);
  gap: 6px;
}
.pipe-flow {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}
.pipe-pending.has-pending {
  color: #d29922;
  font-weight: 500;
}
.pipe-last {
  font-size: 11px;
  color: var(--t3);
  display: flex;
  align-items: center;
  gap: 4px;
}
.pipe-last-ic {
  font-size: 11px;
  vertical-align: -1px;
}
.pipeline-empty {
  grid-column: 1 / -1;
  padding: 28px 0;
  text-align: center;
  color: var(--t2);
  font-size: 13px;
}
.muted { color: var(--t3); }
.mono { font-family: var(--el-font-family-mono, ui-monospace, Menlo, Consolas, monospace); }

.chart-h360 { height: 360px; }
.chart-h280 { height: 280px; }
.chart-h260 { height: 260px; }

/* 最近活动 */
.activity-card { display: flex; flex-direction: column; }
.activity-list {
  flex: 1;
  overflow-y: auto;
  max-height: 260px;
}
.activity-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
  gap: 10px;
}
.activity-item:hover {
  background: var(--bg3);
}
.act-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}
.act-tag {
  flex-shrink: 0;
  font-family: inherit;
}
.act-name {
  color: var(--t1);
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.act-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  flex-shrink: 0;
}
.act-actor {
  font-size: 12px;
  color: var(--t3);
}
.act-ts {
  font-size: 11px;
  color: var(--t2);
}
.activity-empty {
  padding: 40px 0;
  text-align: center;
  color: var(--t2);
  font-size: 13px;
}

/* ── 瓦片缓存卡 ─────────────────────────── */
.tile-card .head-tag { margin-left: 8px; }
.tile-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.3fr);
  gap: 14px;
  margin-top: 4px;
}
@media (max-width: 900px) {
  .tile-body { grid-template-columns: 1fr; }
}
.tile-col {
  background: var(--bg3);
  border: 1px solid var(--bd);
  border-radius: 8px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}
.tile-col-title {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  font-size: 12px;
  font-weight: 600;
  color: var(--t1);
}
.tile-col-title .tile-sub {
  font-size: 11px;
  color: var(--t3);
  font-weight: 400;
}
.tile-prov-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.tile-prov-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  padding: 4px 0;
  border-bottom: 1px dashed rgba(255, 255, 255, 0.04);
}
.tile-prov-row:last-child { border-bottom: none; }
.tp-name { color: var(--t2); }
.tp-spacer { flex: 1; }
.tp-count { color: var(--accent); font-weight: 600; }
.tp-sep { color: var(--t3); }
.tp-bytes { color: var(--t2); font-family: var(--mono, monospace); }
.tile-path {
  margin-top: auto;
  display: flex;
  align-items: center;
  gap: 6px;
  padding-top: 8px;
  border-top: 1px dashed rgba(255, 255, 255, 0.05);
  color: var(--t3);
  font-size: 11px;
  overflow: hidden;
}
.tile-path code {
  font-family: var(--mono, monospace);
  color: var(--t2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
}
.tile-empty {
  padding: 20px 0;
  text-align: center;
  color: var(--t3);
  font-size: 12px;
}
.tile-hist-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 320px;
  overflow-y: auto;
  padding-right: 4px;
}
.tile-hist-row {
  padding: 8px 10px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.04);
  border-radius: 6px;
  font-size: 12px;
  color: var(--t2);
}
.tile-hist-row.err {
  border-color: rgba(248, 81, 73, 0.3);
  background: rgba(248, 81, 73, 0.04);
}
.th-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.th-label {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--t1);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.th-label .th-ic { color: var(--accent); font-size: 12px; }
.th-tag { flex-shrink: 0; }
.th-meta {
  font-size: 11px;
  color: var(--t3);
  margin-bottom: 3px;
}
.th-meta .dot-sep { margin: 0 6px; }
.th-stats {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 11px;
  color: var(--t3);
}
.th-stats .s-item b { color: var(--t1); }
.th-stats .s-item b.ok { color: var(--accent); }
.th-stats .s-item b.err { color: #f85149; }
.th-stats .s-item b.muted { color: var(--t2); }
.th-stats .s-time {
  margin-left: auto;
  color: var(--t2);
}
</style>
