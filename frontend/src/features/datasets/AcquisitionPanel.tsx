import { useEffect, useState } from "react";
import { cancelAcquisition, createAcquisition, fetchAcquisition, fetchSources } from "../../api";
import type { AcquisitionStatus, SourceDefinition } from "../../types";
import { useI18n, type TranslationKey } from "../../i18n";

export function AcquisitionPanel({onChanged,onError}:{onChanged:()=>Promise<void>|void;onError:(message:string)=>void}) {
  const {t}=useI18n();
  const stateLabel=(value:string)=>t(("sources.state."+value) as TranslationKey);
  const [sources,setSources]=useState<SourceDefinition[]>([]);
  const [query,setQuery]=useState('ti="battery"');
  const [limit,setLimit]=useState(100);
  const [job,setJob]=useState<AcquisitionStatus|null>(null);
  const [token,setToken]=useState("");
  const [busy,setBusy]=useState(false);
  useEffect(()=>{fetchSources().then(r=>setSources(r.sources)).catch(e=>onError(e.message));},[]);
  useEffect(()=>{
    if(!job || !["queued","running","publishing"].includes(job.state))return;
    const timer=window.setInterval(()=>{fetchAcquisition(job.id).then(async r=>{
      setJob(r.acquisition);
      if(!["queued","running","publishing"].includes(r.acquisition.state)){window.clearInterval(timer);await onChanged();}
    }).catch(e=>{window.clearInterval(timer);onError(e.message);});},700);
    return ()=>window.clearInterval(timer);
  },[job?.id,job?.state]);
  const send=async(confirm=false)=>{
    setBusy(true);
    try{
      const body=confirm && job ? {...job.request,acquisition_id:job.id,confirmation_token:token}:{source_id:"epo_ops",query,limit,name:"EPO OPS"};
      const {acquisition}=await createAcquisition(body);
      setToken(acquisition.confirmation_token || "");
      setJob({...acquisition,confirmation_token:undefined});
      if(confirm)await onChanged();
    }catch(e){onError((e as Error).message);}finally{setBusy(false);}
  };
  return <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
    <h2 className="font-semibold text-slate-800">{t("sources.title")}</h2>
    <div className="grid gap-2 md:grid-cols-2">{sources.map(source=><details key={source.id} className="rounded-lg border border-slate-200 p-3 text-xs"><summary className="cursor-pointer font-semibold">{source.name} · {stateLabel(source.authorization_status)} · {stateLabel(source.invocation_status)}</summary><a href={source.documentation_url} target="_blank" rel="noreferrer" className="mt-2 block text-blue-600">{t("sources.documentation")}</a><p className="mt-2 break-words">{source.capabilities.join(" · ")}</p>{source.limitations.map((text,i)=><p key={i} className="mt-1 text-slate-500">{text}</p>)}</details>)}</div>
    <label className="block text-xs">{t("sources.query")}<textarea aria-label={t("sources.query")} value={query} onChange={e=>{setQuery(e.target.value);setToken("");}} className="mt-1 w-full rounded-lg border p-2 font-mono text-sm"/></label>
    <label className="block text-xs">{t("sources.limit")}<input aria-label={t("sources.limit")} type="number" min={1} max={1000} value={limit} onChange={e=>{setLimit(Number(e.target.value));setToken("");}} className="ml-3 rounded-lg border p-2"/></label>
    <button disabled={busy || !query.trim() || limit<1 || limit>1000} onClick={()=>send()} className="rounded-lg bg-slate-800 px-4 py-2 text-sm text-white disabled:opacity-50">{t("sources.preview")}</button>
    {job && <div className="space-y-2 rounded-lg bg-slate-50 p-3 text-xs" aria-live="polite"><p>{t("sources.status")}: {stateLabel(job.state)} · {t("sources.pages")}: {job.pages || 0} · {t("sources.records")}: {job.record_count || 0}/{job.total_matched ?? "?"}</p>
      {job.state==="awaiting_confirmation" && token && <><p>{t("sources.disclosure")}</p><dl className="space-y-1 break-all"><dt>{t("sources.query")}</dt><dd className="whitespace-pre-wrap font-mono">{job.request.query}</dd><dt>{t("sources.host")}</dt><dd>https://{job.outbound_host || "ops.epo.org"}</dd><dt>{t("sources.budget")}</dt><dd>{t("sources.records")}: {job.request.limit} · {t("sources.pages")}: 10 · 20 requests · 180 s</dd><dt>{t("sources.expiry")}</dt><dd>{job.expires_at}</dd></dl><button disabled={busy} onClick={()=>send(true)} className="rounded-lg bg-blue-600 px-4 py-2 text-white">{t("sources.confirm")}</button></>}
      {job.state==="credentials_required" && <p className="text-amber-800">{t("sources.credentials")}</p>}
      {job.state==="partial" && <p className="text-amber-800">{t("sources.partial")}</p>}
      {job.state==="completed" && <p>{t("sources.complete")} {job.dataset_version_id}</p>}
      {job.error && <p className="text-rose-700">{job.error}</p>}
      {job.field_status && <details><summary>{t("sources.coverage")}</summary><dl>{Object.entries(job.field_status).map(([field,value])=><div key={field} className="mt-1 flex justify-between"><dt>{field}</dt><dd>{t(("sources.field."+value) as TranslationKey)}</dd></div>)}</dl></details>}
      {["awaiting_confirmation","queued","running"].includes(job.state) && <button onClick={async()=>{try{const r=await cancelAcquisition(job.id);setJob(r.acquisition);setToken("");}catch(e){onError((e as Error).message);}}} className="rounded border px-3 py-1">{t("sources.cancel")}</button>}
    </div>}
  </section>;
}
