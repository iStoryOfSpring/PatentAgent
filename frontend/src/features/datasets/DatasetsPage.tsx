import { useEffect, useRef, useState } from "react";
import { Archive, CheckCircle2, Database, Loader2, UploadCloud } from "lucide-react";
import { bindSessionDataset, fetchImport, loadData, updateDataset, uploadDataset } from "../../api";
import type { DatasetImportStatus, DatasetRecord } from "../../types";
import type { SourceFormat } from "../../api";
import { adapterLabel, importStatusLabel } from "../../uiLabels";

export function DatasetsPage({ datasets, activeSessionId, activeVersionId, onChanged, onError }: {
  datasets: DatasetRecord[];
  activeSessionId: string;
  activeVersionId?: string;
  onChanged: () => Promise<void> | void;
  onError: (message: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [name, setName] = useState("导师演示数据集");
  const [format, setFormat] = useState<SourceFormat>("auto");
  const [uploading, setUploading] = useState(false);
  const [directoryLoading, setDirectoryLoading] = useState(false);
  const [directory, setDirectory] = useState("./my_patents");
  const [job, setJob] = useState<DatasetImportStatus | null>(null);

  useEffect(() => {
    if (!job || !["queued", "parsing"].includes(job.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await fetchImport(job.id);
        setJob(next);
        if (["completed", "failed"].includes(next.status)) {
          window.clearInterval(timer);
          setUploading(false);
          await onChanged();
        }
      } catch (error) {
        window.clearInterval(timer);
        setUploading(false);
        onError((error as Error).message);
      }
    }, 700);
    return () => window.clearInterval(timer);
  }, [job?.id, job?.status]);

  const startUpload = async () => {
    if (!files.length) return;
    setUploading(true);
    try {
      const created = await uploadDataset(files, name, format);
      setJob({ id: created.import_id, status: "queued", created_at: "", updated_at: "", metrics: { progress: 0 } });
    } catch (error) {
      setUploading(false);
      onError((error as Error).message);
    }
  };

  const bind = async (versionId: string) => {
    if (!activeSessionId) return onError("请先创建会话");
    if (activeVersionId !== versionId && !window.confirm("切换数据版本后，当前会话的旧工具证据会标记为过期。继续吗？")) return;
    try {
      await bindSessionDataset(activeSessionId, versionId);
      await onChanged();
    } catch (error) {
      onError((error as Error).message);
    }
  };

  const loadDirectory = async () => {
    setDirectoryLoading(true);
    try {
      await loadData(directory, format);
      await onChanged();
    } catch (error) {
      onError((error as Error).message);
    } finally {
      setDirectoryLoading(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto p-5 md:p-8">
      <div className="mx-auto max-w-6xl space-y-6">
        <div><h1 className="text-2xl font-bold text-slate-900">数据集工作区</h1><p className="mt-1 text-sm text-slate-500">上传官方导出文件，检查字段覆盖，并将不可变版本绑定到会话。</p></div>
        <section className="grid gap-5 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm lg:grid-cols-[1fr_360px]">
          <button type="button" onClick={() => inputRef.current?.click()} className="min-h-44 rounded-2xl border-2 border-dashed border-blue-200 bg-blue-50/50 p-6 text-center hover:border-blue-400">
            <UploadCloud className="mx-auto h-9 w-9 text-blue-600" />
            <div className="mt-3 font-semibold text-slate-800">选择一个或多个专利文件</div>
            <div className="mt-1 text-xs text-slate-500">支持 TXT、JSONL、JSON、XML；JSONL 表示“每行一条 JSON 记录”，暂不支持 ZIP</div>
            {files.length > 0 && <div className="mt-3 text-xs text-blue-700">已选择 {files.length} 个文件 · {(files.reduce((sum, file) => sum + file.size, 0) / 1024 / 1024).toFixed(1)} MB</div>}
            <input ref={inputRef} type="file" multiple accept=".txt,.jsonl,.json,.xml" className="hidden" onChange={event => setFiles(Array.from(event.target.files || []))} />
          </button>
          <div className="space-y-3">
            <label className="block text-xs font-medium text-slate-600">数据集名称<input value={name} onChange={event => setName(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm" /></label>
            <label className="block text-xs font-medium text-slate-600">文件格式<select value={format} onChange={event => setFormat(event.target.value as SourceFormat)} className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"><option value="auto">自动识别（推荐）</option><option value="wos_dii">WoS / Derwent 标记文本（TXT）</option><option value="google_patents_jsonl">Google Patents JSONL（每行一条记录）</option><option value="uspto_grant_xml">USPTO 授权 XML</option><option value="uspto_file_wrapper_json">USPTO File Wrapper JSON（审查档案）</option></select><span className="mt-1 block text-[10px] font-normal text-slate-400">选择来源格式可以减少自动识别歧义；USPTO 是美国专利商标局。</span></label>
            <button onClick={startUpload} disabled={!files.length || uploading} className="flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 py-2.5 text-sm font-semibold text-white disabled:opacity-50">{uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <UploadCloud className="h-4 w-4" />}上传并导入</button>
            {job && <div className={`rounded-lg p-3 text-xs ${job.status === "failed" ? "bg-rose-50 text-rose-700" : "bg-slate-50 text-slate-600"}`}><div className="flex justify-between"><span>{importStatusLabel(job.status)}</span><span>{job.metrics?.progress || 0}%</span></div><div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-200"><div className="h-full bg-blue-600 transition-all" style={{ width: `${job.metrics?.progress || 0}%` }} /></div>{job.error && <p className="mt-2">{job.error}</p>}</div>}
          </div>
        </section>

        <details className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <summary className="cursor-pointer text-sm font-semibold text-slate-700">高级：从本机受控目录导入</summary>
          <div className="mt-4 flex flex-col gap-2 sm:flex-row"><input value={directory} onChange={event => setDirectory(event.target.value)} className="min-w-0 flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm" aria-label="专利数据目录" /><button onClick={loadDirectory} disabled={directoryLoading || !directory.trim()} className="flex items-center justify-center gap-2 rounded-lg bg-slate-800 px-4 py-2 text-sm text-white disabled:opacity-50">{directoryLoading && <Loader2 className="h-4 w-4 animate-spin" />}加载目录</button></div>
          <p className="mt-2 text-[11px] text-slate-400">目录必须位于后端配置的专利数据根目录（PATENT_DATA_ROOT）内；适合大型本地数据或兼容既有工作流。</p>
        </details>

        <section>
          <div className="mb-3 flex items-center justify-between"><h2 className="font-semibold text-slate-800">数据集库</h2><span className="text-xs text-slate-400">{datasets.length} 个数据集</span></div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {datasets.map(dataset => {
              const versionId = dataset.latest_version.id || dataset.latest_version.version_id || "";
              const active = versionId === activeVersionId;
              return <article key={dataset.id} className={`rounded-2xl border bg-white p-4 shadow-sm ${active ? "border-blue-300 ring-2 ring-blue-100" : "border-slate-200"}`}>
                <div className="flex items-start justify-between"><div className="rounded-lg bg-slate-100 p-2 text-slate-600"><Database className="h-5 w-5" /></div>{active && <span className="flex items-center gap-1 text-[10px] text-emerald-600"><CheckCircle2 className="h-3 w-3" />当前会话</span>}</div>
                <h3 className="mt-3 truncate font-semibold text-slate-800">{dataset.name}</h3>
                <p className="mt-1 text-xs text-slate-500">{dataset.latest_version.record_count.toLocaleString()} 件 · {dataset.version_count} 个版本 · {adapterLabel(dataset.latest_version.adapter)}</p>
                <div className="mt-4 grid grid-cols-2 gap-2"><button disabled={active || !versionId} onClick={() => bind(versionId)} className="rounded-lg bg-blue-600 px-3 py-2 text-xs font-medium text-white disabled:bg-slate-200 disabled:text-slate-500">{active ? "已绑定" : "绑定会话"}</button><button onClick={async () => { await updateDataset(dataset.id, { status: "archived" }); await onChanged(); }} className="flex items-center justify-center gap-1 rounded-lg border border-slate-200 px-3 py-2 text-xs text-slate-600"><Archive className="h-3.5 w-3.5" />归档</button></div>
              </article>;
            })}
            {!datasets.length && <div className="col-span-full rounded-2xl border border-dashed border-slate-300 p-10 text-center text-sm text-slate-500">尚无数据集，请先上传官方导出文件。</div>}
          </div>
        </section>
      </div>
    </div>
  );
}
