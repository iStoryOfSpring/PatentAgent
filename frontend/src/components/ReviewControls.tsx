import { useState } from "react";
import { useI18n } from "../i18n";

export type RunReview = (tool:string, params:Record<string,unknown>) => void;
type Row = Record<string,unknown>;
const rows = (v:unknown):Row[] => Array.isArray(v) ? v.filter(x => x && typeof x==="object") : [];
const values = (v:unknown):string[] => Array.isArray(v) ? v.map(String) : [];

export function ReviewControls({result, executionId, onRun}:{result:Row; executionId:string; onRun:RunReview}) {
  const {locale} = useI18n();
  const en = locale==="en-US";
  const [selected,setSelected] = useState(0);
  const [terms,setTerms] = useState<Record<string,string>>({});
  const metadata = result.result_metadata as Row;
  const source = {reviewSourceId:executionId, reviewDigest:metadata?.review_digest};
  if (!["yearly_trend","tech_effect_matrix"].includes(String(result.result_type))) return null;
  if (!source.reviewDigest) return <p className="p-3">{en?"Rerun the source analysis to enable review.":"原执行缺少完整版本证据，请重新分析后复核。"}</p>;
  const buttonClass = "rounded bg-blue-700 px-3 py-2 text-sm text-white";
  if (result.result_type==="yearly_trend") return <div className="p-3">
    <button className={buttonClass} onClick={()=>onRun("audit_trend_robustness", source)}>{en?"Audit annual trend robustness":"核查年度趋势稳健性"}</button>
  </div>;
  if (result.result_type!=="tech_effect_matrix") return null;
  const pairs=rows(result.gap_recommendations);
  if (!pairs.length) return <p className="p-3">{en?"No eligible matrix candidates.":"当前矩阵没有可复核的候选组合。"}</p>;
  const pair=pairs[selected] || pairs[0];
  return <section className="space-y-2 p-3 text-sm">
    <label>{en?"Matrix candidate":"矩阵候选组合"} <select value={selected} onChange={e=>setSelected(Number(e.target.value))}>
      {pairs.map((r,i)=><option key={i} value={i}>{String(r.function)} × {String(r.effect)} ({Number(r.patent_count)})</option>)}
    </select></label>
    <details><summary>{en?"Expand terms and classifications":"扩展词与分类线索"}</summary>
      {Object.entries({technology_terms:en?"Technology synonyms":"技术同义词",effect_terms:en?"Effect synonyms":"功效同义词",
        ipc_prefixes:"IPC",cpc_prefixes:"CPC"}).map(([key,label])=><label className="block" key={key}>{label}
          <input className="ml-2 rounded border" value={terms[key]||""} onChange={e=>setTerms({...terms,[key]:e.target.value})} />
        </label>)}
    </details>
    <button className={buttonClass} onClick={()=>onRun("search_gap_counterevidence", {...source,
      technology:pair.function, effect:pair.effect,...Object.fromEntries(Object.entries(terms).map(([key,text])=>[key,text.split(/[,，\n]/).map(s=>s.trim()).filter(Boolean)]))})}>
      {en?"Search for counterevidence":"检索这个组合的反证"}</button>
  </section>;
}

export function ReviewResults({result}:{result:Row}) {
  const {locale} = useI18n();
  const en=locale==="en-US";
  const label=(code:unknown) => (en?{}:{
    publications:"公开文献",applications:"申请",families:"专利族",increase:"增长",decrease:"下降",flat:"持平",
    incomparable:"不可比",consistent:"方向一致",divergent:"方向分歧",insufficient:"证据不足",unknown:"未知",
    partial:"未覆盖完整尾年",through_year_end:"截止日至少达到尾年末",original:"原词",expanded:"双语与同义词扩展",
    classification:"分类线索",single_axis_lead:"单轴线索",text_both:"双轴文本命中"
  } as Record<string,string>)[String(code)] || String(code);
  if (result.result_type==="trend_robustness") return <section className="space-y-3 p-4 text-sm">
    <h3>{en?"Trend robustness":"趋势稳健性"} · {label(result.verdict)}</h3>
    <p>{en?"Source cutoff":"来源截止日"} {String(result.cutoff || label("unknown"))} · {label(result.tail_coverage)}</p>
    <div className="overflow-auto"><table><thead><tr>{[en?"Unit":"单位",...values(result.years),en?"Change":"差值",en?"Direction":"方向",en?"Continuous increase":"持续增长",en?"Without tail":"去尾年",en?"Missing IDs/dates":"缺标识/日期"].map(h=><th key={h} className="p-2">{h}</th>)}</tr></thead>
    <tbody>{rows(result.data).map(r=><tr key={String(r.unit)}>{[label(r.unit),...values(r.annual_counts),String(r.endpoint_delta??"—"),label(r.direction),r.sustained_growth===null?"—":r.sustained_growth?(en?"Yes":"是"):(en?"No":"否"),label(r.without_tail_direction),r.missing_ids+"/"+r.missing_dates].map((v,i)=><td key={i} className="p-2">{v}</td>)}</tr>)}</tbody></table></div>
    <p>{en?"Grouping examples":"分组与排除示例"} · {String(result.example_total)} {result.examples_truncated===true && (en?"(limited display)":"（仅展示部分）")}</p>
    {rows(result.examples).map((r,i)=><p key={i}>{label(r.unit)} · {String(r.year??"—")} · {String(r.unit_id|| (en?"missing ID":"缺少标识"))} · {values(r.publication_numbers).join(", ")} {r.member_list_truncated===true && "…"}</p>)}
  </section>;
  const source=(result.result_metadata as Row)?.review_source as Row|undefined;
  return <section className="space-y-3 p-4 text-sm">
    <h3>{en?"Counterevidence search":"反证检索结果"} · {String(result.unique_hits)} {en?"unique publications":"件去重候选"}</h3>
    {source && <p>{en?"Original matrix count/sample":"原矩阵观察数/样本量"} {String(source.matrix_observed)}/{String(source.matrix_sample_size)}</p>}
    <p>{en?"Search coverage":"检索范围"} {String(result.reviewed_records)} · {en?"Missing title/abstract":"缺标题/摘要"} {String(result.missing_title)}/{String(result.missing_abstract)} · {en?"Known families / records missing family":"已知族 / 缺族记录"} {String(result.known_families)}/{String(result.missing_family)}</p>
    <p>{en?"Terms (term, source)":"使用词（词、来源）"} · {values(result.technology_terms).join(" / ")} × {values(result.effect_terms).join(" / ")}</p>
    {!result.has_expansions && <p>{en?"No expansion terms supplied or found.":"未提供或匹配到扩展词。"}</p>}
    {rows(result.data).map(r=><section key={String(r.stage)} className="rounded border p-2"><h4>{label(r.stage)} · {String(r.hits)}</h4>
      <p>{en?"New / overlap / new families":"新增 / 重叠 / 新增族"} {String(r.new)} / {String(r.overlap)} / {String(r.new_families)} · {en?"Missing family":"缺族"} {String(r.missing_family)}</p>
      {!r.hits && <p>{en?"No matches in this round.":"本轮零命中。"}</p>}
      {r.truncated===true && <p>{en?"Candidate list truncated.":"候选展示已截断。"}</p>}
      {rows(r.candidates).map(c=><article key={String(c.publication)} className="mt-2"><b>{String(c.publication)}</b> · {label(c.level)} · {c.new?(en?"new":"新增"):(en?"overlap":"重叠")}
        {rows(c.classifications).map((v,i)=><span key={i}> · {String(v.scheme)} {String(v.code)}</span>)}
        {[...rows(c.technology_hits),...rows(c.effect_hits)].map((h,i)=><p key={i}>{String(h.field)} [{String(h.start)}–{String(h.end)}] · {String(h.term)} · <q>{String(h.snippet)}</q></p>)}
      </article>)}
    </section>)}
  </section>;
}
