import { useMemo, useRef, useState } from "react";
import type { ComponentType } from "react";
import type { EChartsCoreOption as EChartsOption } from "echarts/core";
import {
  BarChart3, Download, Expand, Minimize2, MoveHorizontal,
  Shrink, Table2,
} from "lucide-react";
import { EChartCanvas, type EChartCanvasHandle } from "./EChartCanvas";

type ResultRecord = Record<string, unknown>;

interface RendererProps {
  result: ResultRecord;
  fit: boolean;
  chartRef: React.RefObject<EChartCanvasHandle | null>;
}

const COLORS = ["#2563eb", "#0f766e", "#7c3aed", "#ea580c", "#db2777", "#0891b2", "#65a30d", "#475569"];
const axisLine = { lineStyle: { color: "#cbd5e1" } };
const axisLabel = { color: "#64748b", fontSize: 12 };
const splitLine = { lineStyle: { color: "#e2e8f0", type: "dashed" as const } };

function list(value: unknown): ResultRecord[] {
  return Array.isArray(value) ? value.filter(v => v && typeof v === "object") as ResultRecord[] : [];
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

function numbers(value: unknown): number[] {
  return Array.isArray(value) ? value.map(v => Number(v) || 0) : [];
}

function baseOption(title: string): EChartsOption {
  return {
    backgroundColor: "#ffffff",
    color: COLORS,
    animationDuration: 450,
    aria: { enabled: true, decal: { show: true } },
    title: { text: title, left: 24, top: 14, textStyle: { color: "#0f172a", fontSize: 17, fontWeight: 600 } },
    tooltip: { trigger: "axis", backgroundColor: "rgba(15,23,42,.94)", borderWidth: 0, textStyle: { color: "#fff" } },
    toolbox: { right: 20, top: 12, feature: { restore: {}, saveAsImage: { pixelRatio: 2, backgroundColor: "#fff" } } },
  };
}

function TrendRenderer({ result, fit, chartRef }: RendererProps) {
  const data = list(result.data);
  const monthly = result.result_type === "monthly_trend";
  const labels = data.map(d => String(d.year_month ?? d.year ?? ""));
  const values = data.map(d => Number(d.count) || 0);
  const latest = values.length - 1;
  const option: EChartsOption = {
    ...baseOption(monthly ? "专利公开月度趋势" : "专利公开年度趋势"),
    grid: { left: 74, right: 34, top: 78, bottom: labels.length > 24 ? 86 : 58 },
    xAxis: { type: "category", data: labels, boundaryGap: false, axisLine, axisLabel: { ...axisLabel, interval: monthly ? 5 : 0 }, axisTick: { show: false } },
    yAxis: { type: "value", name: "公开量（件）", nameTextStyle: axisLabel, axisLine: { show: false }, axisLabel, splitLine },
    dataZoom: labels.length > 24 ? [
      { type: "inside", start: 0, end: 100 },
      { type: "slider", height: 20, bottom: 20, borderColor: "#e2e8f0", fillerColor: "rgba(37,99,235,.12)" },
    ] : undefined,
    series: [{
      name: "公开量", type: "line", data: values, smooth: 0.25, showSymbol: values.length <= 18,
      symbolSize: 7, lineStyle: { width: 3, color: "#2563eb" }, itemStyle: { color: "#2563eb" },
      areaStyle: { color: "rgba(37,99,235,.10)" }, label: { show: values.length <= 12, position: "top", color: "#475569" },
      markPoint: { symbolSize: 48, label: { fontSize: 10 }, data: [
        { type: "max", name: "最高" }, { type: "min", name: "最低" },
        ...(latest >= 0 ? [{ name: "最新", coord: [labels[latest], values[latest]], value: values[latest] }] : []),
      ] },
    }],
  };
  return <EChartCanvas ref={chartRef} option={option} fit={fit} />;
}

function LifecycleRenderer({ result, fit, chartRef }: RendererProps) {
  const years = strings(result.years);
  const counts = numbers(result.counts);
  const cumulative = numbers(result.cumulative);
  const option: EChartsOption = {
    ...baseOption("年度公开量与累计公开量"),
    legend: { top: 48, textStyle: axisLabel },
    grid: { left: 76, right: 78, top: 92, bottom: 54 },
    xAxis: { type: "category", data: years, axisLine, axisLabel, axisTick: { show: false } },
    yAxis: [
      { type: "value", name: "年度公开量", axisLabel, splitLine },
      { type: "value", name: "累计公开量", axisLabel, splitLine: { show: false } },
    ],
    tooltip: { trigger: "axis" },
    series: [
      { name: "年度公开量", type: "bar", data: counts, barMaxWidth: 46, itemStyle: { color: "#60a5fa", borderRadius: [5, 5, 0, 0] } },
      { name: "累计公开量", type: "line", yAxisIndex: 1, data: cumulative, smooth: true, symbolSize: 8, lineStyle: { width: 3, color: "#0f766e" } },
    ],
  };
  return <EChartCanvas ref={chartRef} option={option} fit={fit} />;
}

function IPCHeatmapRenderer({ result, fit, chartRef }: RendererProps) {
  const years = strings(result.years);
  const sections = strings(result.sections);
  const matrix = Array.isArray(result.matrix) ? result.matrix as unknown[][] : [];
  const values: [number, number, number][] = [];
  matrix.forEach((row, yi) => row.forEach((value, si) => values.push([yi, si, Number(value) || 0])));
  const max = Math.max(1, ...values.map(v => v[2]));
  const option: EChartsOption = {
    ...baseOption(String((result.result_metadata as ResultRecord | undefined)?.metric_label || "IPC 标注次数") + "年度分布"),
    tooltip: { position: "top", formatter: (p: unknown) => {
      const value = (p as { value: number[] }).value;
      return `${years[value[0]]} · IPC ${sections[value[1]]}<br/><b>${value[2].toLocaleString()} · ${String((result.result_metadata as ResultRecord | undefined)?.metric_label || "IPC 标注次数")}</b>`;
    } },
    grid: { left: 82, right: 100, top: 78, bottom: 64 },
    xAxis: { type: "category", data: years, splitArea: { show: true }, axisLine, axisLabel },
    yAxis: { type: "category", data: sections, splitArea: { show: true }, axisLine, axisLabel },
    visualMap: { min: 0, max, right: 18, top: "middle", calculable: true, inRange: { color: ["#eff6ff", "#93c5fd", "#2563eb", "#1e3a8a"] } },
    series: [{ type: "heatmap", data: values, label: { show: values.length <= 80, color: "#0f172a" }, emphasis: { itemStyle: { shadowBlur: 8, shadowColor: "rgba(15,23,42,.25)" } } }],
  };
  return <EChartCanvas ref={chartRef} option={option} fit={fit} />;
}

function WordFrequencyRenderer({ result, fit, chartRef }: RendererProps) {
  const [tab, setTab] = useState<"cloud" | "bar">("cloud");
  const data = list(result.data).slice(0, 100);
  const top = data.slice(0, 20).reverse();
  const cloudWords = data.slice(0, 55);
  const maxCount = Math.max(1, ...cloudWords.map(d => Number(d.count) || 0));
  let cloudX = 62; let cloudY = 92; let rowHeight = 0;
  const cloudGraphics = cloudWords.flatMap((item, index) => {
    const count = Number(item.count) || 0;
    const fontSize = 14 + Math.round(38 * Math.sqrt(count / maxCount));
    const word = String(item.word);
    const estimatedWidth = Math.max(50, word.length * fontSize * .62) + 22;
    if (cloudX + estimatedWidth > 900) { cloudX = 62; cloudY += rowHeight + 16; rowHeight = 0; }
    if (cloudY + fontSize > 485) return [];
    const graphic = { type: "text", left: cloudX, top: cloudY, style: { text: word, fill: COLORS[index % COLORS.length], fontSize, fontWeight: index < 8 ? 600 : 400 } };
    cloudX += estimatedWidth; rowHeight = Math.max(rowHeight, fontSize);
    return [graphic];
  });
  const option: EChartsOption = tab === "cloud" ? {
    ...baseOption("技术关键词云"),
    graphic: cloudGraphics,
  } : {
    ...baseOption("技术关键词 Top 20"),
    grid: { left: 150, right: 50, top: 72, bottom: 34 },
    xAxis: { type: "value", axisLabel, splitLine },
    yAxis: { type: "category", data: top.map(d => String(d.word)), axisLabel: { ...axisLabel, width: 125, overflow: "truncate" }, axisLine, axisTick: { show: false } },
    series: [{ type: "bar", data: top.map(d => Number(d.count) || 0), barMaxWidth: 18, label: { show: true, position: "right", color: "#475569" }, itemStyle: { color: "#2563eb", borderRadius: [0, 4, 4, 0] } }],
  };
  return <div><div className="mb-2 flex justify-center gap-1"><TabButton active={tab === "cloud"} onClick={() => setTab("cloud")}>词云</TabButton><TabButton active={tab === "bar"} onClick={() => setTab("bar")}>Top 20</TabButton></div><EChartCanvas ref={chartRef} option={option} fit={fit} /></div>;
}

function BurstRenderer({ result, fit, chartRef }: RendererProps) {
  const data = list(result.data).slice(0, 20).reverse();
  const option: EChartsOption = {
    ...baseOption("近期增长词"),
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, formatter: (params: unknown) => {
      const item = (Array.isArray(params) ? params[0] : params) as { dataIndex: number };
      const row = data[item.dataIndex] || {};
      return `${row.term}<br/>增长分数：<b>${row.burst}</b><br/>历史支持：${row.early_freq ?? "-"}<br/>近期支持：${row.late_freq ?? "-"}`;
    } },
    grid: { left: 160, right: 64, top: 74, bottom: 34 },
    xAxis: { type: "value", name: "近期增长分数", axisLabel, splitLine },
    yAxis: { type: "category", data: data.map(d => String(d.term)), axisLabel: { ...axisLabel, width: 135, overflow: "truncate" }, axisLine, axisTick: { show: false } },
    series: [{ type: "bar", data: data.map(d => Number(d.burst) || 0), barMaxWidth: 18, label: { show: true, position: "right", color: "#475569" }, itemStyle: { color: "#ea580c", borderRadius: [0, 4, 4, 0] } }],
  };
  return <EChartCanvas ref={chartRef} option={option} fit={fit} height={600} />;
}

function YearlyKeywordsRenderer({ result, fit, chartRef }: RendererProps) {
  const source = result.data && typeof result.data === "object" ? result.data as Record<string, unknown> : {};
  const years = Object.keys(source).sort();
  const totals = new Map<string, number>();
  years.forEach(year => (Array.isArray(source[year]) ? source[year] : []).forEach(item => {
    if (!Array.isArray(item)) return;
    totals.set(String(item[0]), (totals.get(String(item[0])) || 0) + (Number(item[1]) || 0));
  }));
  const terms = [...totals.entries()].sort((a, b) => b[1] - a[1]).slice(0, 18).map(([term]) => term);
  const heat: [number, number, number][] = [];
  years.forEach((year, yi) => {
    const values = new Map((Array.isArray(source[year]) ? source[year] : []).filter(Array.isArray).map(item => [String(item[0]), Number(item[1]) || 0]));
    terms.forEach((term, ti) => heat.push([yi, ti, values.get(term) || 0]));
  });
  const option: EChartsOption = {
    ...baseOption("逐年技术关键词热力图"),
    tooltip: { formatter: (p: unknown) => { const v = (p as { value: number[] }).value; return `${years[v[0]]} · ${terms[v[1]]}<br/><b>${v[2]}</b>`; } },
    grid: { left: 150, right: 100, top: 76, bottom: 58 },
    xAxis: { type: "category", data: years, axisLine, axisLabel },
    yAxis: { type: "category", data: terms, axisLine, axisLabel: { ...axisLabel, width: 125, overflow: "truncate" } },
    visualMap: { min: 0, max: Math.max(1, ...heat.map(v => v[2])), right: 18, top: "middle", inRange: { color: ["#f8fafc", "#bfdbfe", "#3b82f6", "#1e3a8a"] } },
    series: [{ type: "heatmap", data: heat, label: { show: heat.length <= 60 } }],
  };
  return <EChartCanvas ref={chartRef} option={option} fit={fit} height={620} />;
}

function NetworkRenderer({ result, fit, chartRef }: RendererProps) {
  const edges = list(result.edges);
  if (!edges.length) return <EmptyState title="合作网络证据不足" text="当前筛选范围内没有可形成关系图的共同申请记录。" />;
  const degree = new Map<string, number>();
  edges.forEach(edge => {
    const source = String(edge.source); const target = String(edge.target); const weight = Number(edge.weight) || 1;
    degree.set(source, (degree.get(source) || 0) + weight); degree.set(target, (degree.get(target) || 0) + weight);
  });
  const max = Math.max(...degree.values(), 1);
  const nodes = [...degree.entries()].map(([name, value]) => ({ name, value, symbolSize: 14 + 42 * value / max, label: { show: value >= max * .35 } }));
  const option: EChartsOption = {
    ...baseOption("申请人合作网络"),
    tooltip: { formatter: (p: unknown) => { const d = (p as { data: { name?: string; value?: number; source?: string; target?: string } }).data; return d.name ? `${d.name}<br/>连接强度：${d.value}` : `${d.source} ↔ ${d.target}`; } },
    series: [{ type: "graph", layout: "force", roam: true, draggable: true, data: nodes, links: edges.map(e => ({ source: String(e.source), target: String(e.target), value: Number(e.weight) || 1 })),
      force: { repulsion: 420, edgeLength: [70, 220], gravity: .08 }, lineStyle: { color: "source", opacity: .3, curveness: .08 }, label: { position: "right", color: "#334155", fontSize: 11 }, emphasis: { focus: "adjacency", lineStyle: { width: 3, opacity: .8 } } }],
  };
  return <EChartCanvas ref={chartRef} option={option} fit={fit} width={1100} height={680} />;
}

function CountryRenderer({ result, fit, chartRef }: RendererProps) {
  const all = list(result.data).sort((a, b) => Number(b.count) - Number(a.count));
  const top = all.slice(0, 10).map(d => ({ name: String(d.country), value: Number(d.count) || 0 }));
  const other = all.slice(10).reduce((sum, d) => sum + (Number(d.count) || 0), 0);
  if (other) top.push({ name: "其他", value: other });
  const option: EChartsOption = {
    ...baseOption("主公开号首次公开局分布"),
    legend: { orient: "vertical", left: 42, top: 92, textStyle: axisLabel },
    tooltip: { trigger: "item", formatter: "{b}<br/><b>{c} 件</b>（{d}%）" },
    series: [{ type: "pie", radius: ["40%", "70%"], center: ["62%", "54%"], avoidLabelOverlap: true, data: top,
      label: { formatter: "{b}\n{d}%", color: "#475569" }, itemStyle: { borderColor: "#fff", borderWidth: 2 } }],
  };
  return <EChartCanvas ref={chartRef} option={option} fit={fit} />;
}

function DatasetRenderer({ result }: RendererProps) {
  const applicants = list(result.top_applicants);
  return <div className="p-5 space-y-5">
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
      <Kpi label="专利总量" value={`${Number(result.total_patents || 0).toLocaleString()} 件`} />
      <Kpi label="公开时间跨度" value={`${result.year_start || "—"}–${result.year_end || "—"}`} />
      <Kpi label="IPC 部级分类" value={strings(result.ipc_sections).join(" · ") || "—"} />
    </div>
    <SimpleTable rows={applicants.map((r, i) => ({ rank: i + 1, applicant: r.name, count: r.count }))} labels={{ rank: "#", applicant: "主要申请人", count: "专利数" }} />
  </div>;
}

function RoadmapRenderer({ result }: RendererProps) {
  const data = result.data && typeof result.data === "object" ? result.data as Record<string, unknown> : {};
  const years = Object.keys(data).sort();
  if (!years.length) return <EmptyState title="暂无年度主题时间线" text="当前筛选范围没有可用的年度代表性专利。" />;
  return <div className="overflow-x-auto p-5"><div className="flex gap-5 min-w-max pb-3">
    {years.map(year => <div key={year} className="w-72 shrink-0">
      <div className="flex items-center gap-2 mb-3"><span className="w-3 h-3 bg-blue-600 rounded-full"/><h4 className="font-semibold text-slate-800">{year}</h4></div>
      <div className="space-y-2 border-l-2 border-blue-100 pl-4">
        {list(data[year]).map((item, i) => <div key={i} className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
          <div className="font-mono text-xs text-blue-700 mb-1">{String(item.patent_number || "")}</div>
          <p className="text-xs leading-5 text-slate-600 line-clamp-4" title={String(item.title || "")}>{String(item.title || "")}</p>
          {Array.isArray(item.annual_themes) && <div className="mt-2 flex flex-wrap gap-1">{strings(item.annual_themes).slice(0, 4).map(t => <span key={t} className="text-[10px] px-1.5 py-.5 rounded bg-blue-50 text-blue-700">{t}</span>)}</div>}
        </div>)}
      </div>
    </div>)}
  </div></div>;
}

function SearchRenderer({ result }: RendererProps) {
  const patents = list(result.patents);
  if (!patents.length) return <EmptyState title="没有匹配结果" text="请扩大检索词、年份或 IPC 范围后重试。" />;
  return <div className="p-4 grid gap-3">{patents.map((patent, i) => {
    const score = Number(patent.relevance_score) || 0;
    return <div key={`${patent.patent_number}-${i}`} className="border border-slate-200 rounded-xl p-4 bg-white">
      <div className="flex gap-3 justify-between"><div><span className="font-mono text-xs text-blue-700">{String(patent.patent_number || "")}</span><h4 className="font-medium text-slate-800 mt-1">{String(patent.title || "")}</h4></div><span className="text-xs font-semibold text-blue-700">排序分数 {score.toFixed(4)}</span></div>
      <p className="text-xs text-slate-500 mt-2 line-clamp-2">{String(patent.abstract || patent.applicants || "")}</p>
    </div>;
  })}</div>;
}

function PatentDetailsRenderer({ result }: RendererProps) {
  const patents = list(result.patents);
  if (!patents.length) return <EmptyState title="未找到专利详情" text="请检查公开号是否存在于当前数据集。" />;
  return <div className="p-4 space-y-2">{patents.map((patent, i) => <details key={i} open={i === 0} className="border border-slate-200 rounded-xl bg-white overflow-hidden">
    <summary className="cursor-pointer px-4 py-3 font-medium text-slate-800 bg-slate-50"><span className="font-mono text-blue-700 mr-2">{String(patent.patent_number || "")}</span>{String(patent.title || "")}</summary>
    <div className="p-4 grid gap-3 text-sm text-slate-600"><p>{String(patent.abstract || "暂无摘要")}</p><SimpleTable rows={[{ applicants: Array.isArray(patent.applicants) ? strings(patent.applicants).join("；") : patent.applicants, publication_date: patent.publication_date, legal_status: patent.legal_status || "不可用", backward_citations: Array.isArray(patent.backward_citations) ? patent.backward_citations.length : 0 }]} labels={{ applicants: "申请人", publication_date: "公开日", legal_status: "法律状态", backward_citations: "后向引证" }}/></div>
  </details>)}</div>;
}

function TechMatrixRenderer({ result }: RendererProps) {
  const functions = strings(result.functions).slice(0, 15);
  const effects = strings(result.effects).slice(0, 10);
  const matrix = Array.isArray(result.matrix) ? result.matrix as unknown[][] : [];
  const max = Math.max(1, ...matrix.flat().map(Number).filter(Number.isFinite));
  const gaps = list(result.gap_recommendations).slice(0, 10);
  return <div className="grid xl:grid-cols-[minmax(720px,1fr)_300px] gap-5 p-4">
    <div className="overflow-x-auto"><table className="min-w-[720px] w-full text-xs border-separate border-spacing-1"><thead><tr><th className="sticky left-0 bg-white"/>{effects.map(e => <th key={e} className="p-2 text-slate-600 font-medium max-w-24 truncate" title={e}>{e}</th>)}</tr></thead><tbody>{functions.map((f, i) => <tr key={f}><th className="sticky left-0 bg-white p-2 text-left text-slate-700 font-medium max-w-36 truncate" title={f}>{f}</th>{effects.map((e, j) => { const value = Number(matrix[i]?.[j]) || 0; const alpha = .08 + .82 * value / max; return <td key={e} title={`${f} × ${e}: ${value} 件`} className="h-10 text-center rounded text-slate-900" style={{ backgroundColor: `rgba(37,99,235,${alpha})`, color: alpha > .55 ? "white" : "#0f172a" }}>{value}</td>; })}</tr>)}</tbody></table></div>
    <div><h4 className="font-semibold text-slate-800 mb-2">低共现复核候选</h4><div className="space-y-2">{gaps.map((g, i) => <div key={i} className="rounded-lg bg-amber-50 border border-amber-100 p-2 text-xs"><div className="font-medium text-amber-900">{String(g.function)} × {String(g.effect)}</div><div className="text-amber-700 mt-1">相关专利 {Number(g.patent_count) || 0} 件 · 需人工复核</div></div>)}</div></div>
  </div>;
}

function ClusteringRenderer({ result, fit, chartRef }: RendererProps) {
  const counts = result.patents_per_cluster && typeof result.patents_per_cluster === "object" ? result.patents_per_cluster as Record<string, unknown> : {};
  const titles = result.cluster_titles && typeof result.cluster_titles === "object" ? result.cluster_titles as Record<string, unknown> : {};
  const keywords = result.cluster_keywords && typeof result.cluster_keywords === "object" ? result.cluster_keywords as Record<string, unknown> : {};
  const ids = Object.keys(counts).sort((a, b) => Number(counts[a]) - Number(counts[b]));
  const option: EChartsOption = {
    ...baseOption(`聚类规模分布 · silhouette ${result.silhouette_score == null ? "—" : Number(result.silhouette_score).toFixed(3)}`),
    grid: { left: 210, right: 70, top: 76, bottom: 36 }, xAxis: { type: "value", axisLabel, splitLine },
    yAxis: { type: "category", data: ids.map(id => String(titles[id] || `Cluster ${id}`)), axisLabel: { ...axisLabel, width: 185, overflow: "truncate" }, axisLine },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, formatter: (params: unknown) => { const p = (Array.isArray(params) ? params[0] : params) as { dataIndex: number; value: number }; const id = ids[p.dataIndex]; return `${titles[id] || `Cluster ${id}`}<br/><b>${p.value} 件</b><br/>${strings(keywords[id]).slice(0, 8).join(" · ")}`; } },
    series: [{ type: "bar", data: ids.map(id => Number(counts[id]) || 0), label: { show: true, position: "right", color: "#475569" }, barMaxWidth: 28, itemStyle: { color: "#7c3aed", borderRadius: [0, 5, 5, 0] } }],
  };
  return <EChartCanvas ref={chartRef} option={option} fit={fit} height={Math.max(480, ids.length * 48 + 130)} />;
}

function ValuationRenderer({ result, fit, chartRef }: RendererProps) {
  const rows = list(result.data).slice(0, 10).reverse();
  const label = String(result.score_label || "价值筛查分");
  const option: EChartsOption = {
    ...baseOption(`${label} Top ${rows.length}`), grid: { left: 170, right: 70, top: 76, bottom: 36 },
    xAxis: { type: "value", name: label, max: 100, axisLabel, splitLine }, yAxis: { type: "category", data: rows.map(r => String(r.patent_number)), axisLabel: { ...axisLabel, fontFamily: "monospace" }, axisLine },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, formatter: (params: unknown) => { const p = (Array.isArray(params) ? params[0] : params) as { dataIndex: number }; const row = rows[p.dataIndex] || {}; const interval = Array.isArray(row.score_interval) ? row.score_interval : []; return `${row.patent_number}<br/>${label}：<b>${Number(row.score || 0).toFixed(1)}</b>${interval.length === 2 ? `<br/>不确定区间：${Number(interval[0]).toFixed(1)}–${Number(interval[1]).toFixed(1)}` : ""}<br/>同族规模：${row.family_size ?? "缺失"} · IPC小类广度：${row.ipc_breadth ?? "缺失"}<br/>专利年龄：${row.patent_age ?? "缺失"}<br/>可用权重：${(Number(row.available_weight_ratio || 0) * 100).toFixed(0)}% · 置信：${row.confidence_level ?? "未知"}`; } },
    series: [{ type: "bar", data: rows.map(r => Number(r.score) || 0), label: { show: true, position: "right", formatter: "{c}", color: "#475569" }, barMaxWidth: 24, itemStyle: { color: "#0f766e", borderRadius: [0, 5, 5, 0] } }],
  };
  return <EChartCanvas ref={chartRef} option={option} fit={fit} height={Math.max(520, rows.length * 42 + 130)} />;
}

function CompetitorRenderer({ result, fit, chartRef }: RendererProps) {
  const data = result.data && typeof result.data === "object" ? result.data as Record<string, unknown> : {};
  const evolution = list(data.evolution);
  const [selected, setSelected] = useState(0);
  if (!evolution.length) return <EmptyState title="竞对演化数据不足" text="至少需要同一申请人跨两个公开年度的 IPC 数据。" />;
  const current = evolution[Math.min(selected, evolution.length - 1)];
  const years = strings(current.years);
  const option: EChartsOption = {
    ...baseOption(`${String(current.applicant)} · IPC 画像演化`), legend: { top: 48, textStyle: axisLabel }, grid: { left: 76, right: 55, top: 92, bottom: 58 },
    xAxis: { type: "category", data: years, axisLine, axisLabel }, yAxis: { type: "value", axisLabel, splitLine }, tooltip: { trigger: "axis" },
    series: [
      { name: "IPC entropy", type: "line", data: numbers(current.ipc_entropy), smooth: true, symbolSize: 7 },
      { name: "dominant IPC share", type: "line", data: numbers(current.dominant_ipc_share), smooth: true, symbolSize: 7 },
      { name: "IPC cosine shift", type: "line", data: numbers(current.ipc_profile_cosine_shift), smooth: true, symbolSize: 7 },
    ],
  };
  const topIpc = Array.isArray(current.top_ipc) ? current.top_ipc as unknown[][] : [];
  return <div><div className="p-3 flex flex-wrap gap-2 items-center"><label className="text-xs text-slate-500">申请人</label><select value={selected} onChange={e => setSelected(Number(e.target.value))} className="max-w-md border border-slate-200 rounded-lg px-3 py-1.5 text-sm bg-white">{evolution.map((e, i) => <option key={i} value={i}>{String(e.applicant)}（{Number(e.total_patents).toLocaleString()} 件）</option>)}</select><span className="text-xs text-slate-500">{String(current.trend_summary || "")}</span></div><EChartCanvas ref={chartRef} option={option} fit={fit}/><div className="px-5 pb-4 flex gap-3 overflow-x-auto">{years.map((year, i) => <div key={year} className="shrink-0 text-xs border border-slate-200 rounded-lg p-2"><b>{year}</b><div className="mt-1 flex gap-1">{strings(topIpc[i]).map(code => <span key={code} className="bg-blue-50 text-blue-700 px-1.5 rounded">{code}</span>)}</div></div>)}</div></div>;
}

function GenericStructuredRenderer({ result }: RendererProps) {
  const rows = list(result.data);
  const metadata = result.result_metadata && typeof result.result_metadata === "object"
    ? result.result_metadata as ResultRecord : {};
  const warnings = strings(result.warnings);
  return <div className="p-5 space-y-4">
    <div className="rounded-xl border border-blue-100 bg-blue-50/60 p-4">
      <div className="text-sm font-medium text-slate-800">{String(result.summary || "结构化分析结果")}</div>
      {warnings.map((warning, index) => <p key={index} className="mt-1 text-xs leading-5 text-amber-800">⚠ {warning}</p>)}
    </div>
    {rows.length ? <SimpleTable rows={rows.slice(0, 200)}/> : <EmptyState title="暂无结果记录" text="当前作用域内没有满足条件的分析记录。"/>}
    <details className="rounded-xl border border-slate-200 bg-white">
      <summary className="cursor-pointer px-4 py-3 text-xs font-semibold text-slate-700">口径、覆盖与审计元数据</summary>
      <pre className="border-t border-slate-100 p-4 max-h-72 overflow-auto text-xs leading-5 text-slate-600">{JSON.stringify(metadata, null, 2)}</pre>
    </details>
  </div>;
}

function ClaimReviewRenderer({ result }: RendererProps) {
  const patents = list(result.data);
  const [reviewed, setReviewed] = useState<Record<string, boolean>>({});
  const toggle = (key: string) => setReviewed(current => ({ ...current, [key]: !current[key] }));
  return <div className="p-5 space-y-4">
    <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
      <div className="text-sm font-semibold text-amber-950">人工复核草稿</div>
      <p className="mt-1 text-xs leading-5 text-amber-800">要素拆分和产品特征映射仅按规则与词面匹配生成，不构成侵权、等同、无效或 FTO 结论。下列勾选只记录当前界面的复核进度，导出 JSON 后应进入正式法律审阅流程。</p>
    </div>
    {patents.map((patent, patentIndex) => <section key={patentIndex} className="rounded-xl border border-slate-200 overflow-hidden">
      <header className="px-4 py-3 bg-slate-50 text-sm font-semibold text-slate-800">
        <span className="font-mono text-blue-700 mr-2">{String(patent.patent_number || "")}</span>
        {String(patent.kind_code || "版本未知")} · {String(patent.legal_status || "状态未知")}
      </header>
      <div className="divide-y divide-slate-100">{list(patent.claims).map((claim, claimIndex) => {
        const key = `${patent.patent_number}:${claim.claim_number}`;
        return <div key={key} className="p-4">
          <label className="flex items-center gap-2 text-sm font-medium text-slate-800">
            <input type="checkbox" checked={Boolean(reviewed[key])} onChange={() => toggle(key)} />
            权利要求 {String(claim.claim_number)} · {claim.is_independent ? "独立" : "从属"} · {String(claim.language || "und")}
          </label>
          <div className="mt-3 space-y-2">{list(claim.elements).map((element, elementIndex) => <div key={elementIndex} className="rounded-lg border border-slate-100 bg-slate-50 p-3 text-xs leading-5 text-slate-700"><b className="mr-2">要素 {String(element.element_number)}</b>{String(element.text || "")}</div>)}</div>
          <div className="mt-3"><SimpleTable rows={list(claim.product_feature_mapping_draft)} labels={{ feature: "产品特征", matched_element_numbers: "词面匹配要素", match_method: "匹配方法" }}/></div>
          <p className="mt-2 font-mono text-[10px] text-slate-400 break-all">{String(claim.source_evidence_path || "")} · {String(claim.source_text_sha256 || "")}</p>
        </div>;
      })}</div>
    </section>)}
  </div>;
}

const visualizationRegistry: Record<string, ComponentType<RendererProps>> = {
  monthly_trend: TrendRenderer,
  yearly_trend: TrendRenderer,
  s_curve: LifecycleRenderer,
  ipc_matrix: IPCHeatmapRenderer,
  word_freq: WordFrequencyRenderer,
  burst_terms: BurstRenderer,
  yearly_keywords: YearlyKeywordsRenderer,
  co_occurrence: NetworkRenderer,
  network: NetworkRenderer,
  country_distribution: CountryRenderer,
  dataset_summary: DatasetRenderer,
  roadmap: RoadmapRenderer,
  patent_search: SearchRenderer,
  patent_details: PatentDetailsRenderer,
  tech_effect_matrix: TechMatrixRenderer,
  clustering: ClusteringRenderer,
  value_indicators: ValuationRenderer,
  competitor_evolution: CompetitorRenderer,
  entity_portfolio: GenericStructuredRenderer,
  concentration: GenericStructuredRenderer,
  citation_network: GenericStructuredRenderer,
  family_geography: GenericStructuredRenderer,
  search_strategy_audit: GenericStructuredRenderer,
  legal_status: GenericStructuredRenderer,
  patent_monitor: GenericStructuredRenderer,
  claim_elements: ClaimReviewRenderer,
};

export function VisualizationPanel({ result, chartHtml, toolName }: { result?: ResultRecord | null; chartHtml?: string | null; toolName: string }) {
  const [view, setView] = useState<"visual" | "data">("visual");
  const [fit, setFit] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const chartRef = useRef<EChartCanvasHandle>(null);
  const resultType = String(result?.result_type || "");
  const Renderer = visualizationRegistry[resultType];
  const hasStructured = Boolean(Renderer && result);

  const download = () => {
    if (view === "visual" && chartRef.current) {
      chartRef.current.exportPng(`${toolName}_${resultType || "chart"}`);
      return;
    }
    const blob = new Blob([JSON.stringify(result || {}, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob); const anchor = document.createElement("a");
    anchor.href = url; anchor.download = `${toolName}_${resultType || "result"}.json`; anchor.click(); URL.revokeObjectURL(url);
  };

  if (!hasStructured && !chartHtml && !result) return null;
  return <div className={fullscreen ? "visualization-fullscreen fixed inset-4 z-50 bg-white rounded-2xl shadow-2xl border border-slate-200 flex flex-col" : "border-t border-slate-100 bg-white"}>
    {fullscreen && <div className="fixed inset-0 -z-10 bg-slate-950/45" onClick={() => setFullscreen(false)}/>} 
    <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 border-b border-slate-100 bg-slate-50/80">
      <div className="flex rounded-lg border border-slate-200 bg-white p-0.5">
        <ToolbarButton active={view === "visual"} onClick={() => setView("visual")} icon={<BarChart3 className="w-3.5 h-3.5"/>}>图表</ToolbarButton>
        <ToolbarButton active={view === "data"} onClick={() => setView("data")} icon={<Table2 className="w-3.5 h-3.5"/>}>数据</ToolbarButton>
      </div>
      <div className="flex items-center gap-1">
        {view === "visual" && hasStructured && <ToolbarButton active={fit} onClick={() => setFit(v => !v)} icon={fit ? <Shrink className="w-3.5 h-3.5"/> : <MoveHorizontal className="w-3.5 h-3.5"/>}>{fit ? "原始尺寸" : "适应窗格"}</ToolbarButton>}
        <ToolbarButton onClick={download} icon={<Download className="w-3.5 h-3.5"/>}>{view === "visual" ? "导出 PNG" : "导出 JSON"}</ToolbarButton>
        <ToolbarButton onClick={() => setFullscreen(v => !v)} icon={fullscreen ? <Minimize2 className="w-3.5 h-3.5"/> : <Expand className="w-3.5 h-3.5"/>}>{fullscreen ? "退出全屏" : "全屏"}</ToolbarButton>
      </div>
    </div>
    <div className={fullscreen ? "flex-1 overflow-auto p-4" : "overflow-hidden"}>
      {view === "data" ? <ResultDataView result={result || {}}/> : hasStructured && result ? <Renderer result={result} fit={fit || fullscreen} chartRef={chartRef}/> : <EmptyState title="旧版 HTML 图表已禁用" text="为防止数据集内脚本执行，请切换到数据视图查看结构化结果。"/>}
    </div>
  </div>;
}

function ResultDataView({ result }: { result: ResultRecord }) {
  const rows = useMemo(() => {
    for (const key of ["data", "patents", "top_applicants", "edges", "nodes", "gap_recommendations"]) {
      const value = result[key]; if (Array.isArray(value) && value.length && typeof value[0] === "object") return value as ResultRecord[];
    }
    return [];
  }, [result]);
  if (rows.length) return <div className="p-4"><SimpleTable rows={rows.slice(0, 200)}/>{rows.length > 200 && <p className="mt-2 text-xs text-slate-500">仅显示前 200 行，共 {rows.length} 行；导出 JSON 可查看完整结果。</p>}</div>;
  return <pre className="m-4 p-4 max-h-[620px] overflow-auto rounded-xl bg-slate-950 text-slate-100 text-xs leading-5">{JSON.stringify(result, null, 2)}</pre>;
}

function SimpleTable({ rows, labels = {} }: { rows: ResultRecord[]; labels?: Record<string, string> }) {
  const [scrollTop, setScrollTop] = useState(0);
  if (!rows.length) return <EmptyState title="暂无结构化记录" text="当前结果没有可显示的数据行。"/>;
  const columns = [...new Set(rows.flatMap(row => Object.keys(row)))].slice(0, 12);
  const rowHeight = 37;
  const virtual = rows.length > 80;
  const start = virtual ? Math.max(0, Math.floor(scrollTop / rowHeight) - 8) : 0;
  const end = virtual ? Math.min(rows.length, start + Math.ceil(560 / rowHeight) + 16) : rows.length;
  const visibleRows = rows.slice(start, end);
  return <div onScroll={event => setScrollTop(event.currentTarget.scrollTop)} className="overflow-auto max-h-[560px] border border-slate-200 rounded-xl"><table className="min-w-full text-xs"><thead className="sticky top-0 bg-slate-100 z-10"><tr>{columns.map(c => <th key={c} className="text-left px-3 py-2 font-semibold text-slate-600 whitespace-nowrap">{labels[c] || c}</th>)}</tr></thead><tbody className="divide-y divide-slate-100">
    {virtual && start > 0 && <tr aria-hidden="true"><td colSpan={columns.length} style={{ height: start * rowHeight, padding: 0 }}/></tr>}
    {visibleRows.map((row, offset) => <tr key={start + offset} style={{ height: rowHeight }} className="hover:bg-blue-50/40">{columns.map(c => <td key={c} className="px-3 py-2 text-slate-600 max-w-72 truncate" title={formatCell(row[c])}>{formatCell(row[c])}</td>)}</tr>)}
    {virtual && end < rows.length && <tr aria-hidden="true"><td colSpan={columns.length} style={{ height: (rows.length - end) * rowHeight, padding: 0 }}/></tr>}
  </tbody></table></div>;
}

function formatCell(value: unknown): string {
  if (value == null || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function ToolbarButton({ children, icon, active = false, onClick }: { children: React.ReactNode; icon?: React.ReactNode; active?: boolean; onClick: () => void }) {
  return <button onClick={onClick} className={`flex items-center gap-1 px-2.5 py-1.5 rounded-md text-[11px] transition-colors ${active ? "bg-blue-600 text-white" : "text-slate-600 hover:bg-slate-100"}`}>{icon}{children}</button>;
}

function TabButton({ children, active, onClick }: { children: React.ReactNode; active: boolean; onClick: () => void }) {
  return <button onClick={onClick} className={`px-3 py-1 rounded-full text-xs ${active ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-600"}`}>{children}</button>;
}

function Kpi({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl border border-slate-200 bg-gradient-to-br from-white to-blue-50 p-4"><div className="text-xs text-slate-500">{label}</div><div className="mt-1 text-xl font-semibold text-slate-900">{value}</div></div>;
}

function EmptyState({ title, text }: { title: string; text: string }) {
  return <div className="m-4 min-h-48 rounded-xl border border-dashed border-slate-300 bg-slate-50 flex flex-col items-center justify-center text-center p-8"><BarChart3 className="w-8 h-8 text-slate-300 mb-3"/><h4 className="font-medium text-slate-700">{title}</h4><p className="text-xs text-slate-500 mt-1 max-w-md">{text}</p></div>;
}
