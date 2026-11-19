import { useEffect, useRef, useState } from "react";
import { fetchExecutionRecords } from "../api";
import type { ExecutionRecordPage } from "../types";
import { useI18n, type TranslationKey } from "../i18n";

interface Props { executionId: string; bins: string[] }

export function ExecutionEvidence(props: Props) {
  return <EvidencePanel key={JSON.stringify([props.executionId, props.bins])} {...props} />;
}

function EvidencePanel({ executionId, bins }: Props) {
  const { t } = useI18n();
  const [bin, setBin] = useState(bins[0] || "");
  const [page, setPage] = useState<ExecutionRecordPage | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const sequence = useRef(0);
  useEffect(() => () => { sequence.current++; }, []);

  function selectBin(value: string) {
    sequence.current++;
    setBin(value);
    setPage(null);
    setError("");
    setBusy(false);
  }

  async function load(offset = 0) {
    const request = ++sequence.current;
    setBusy(true);
    setError("");
    try {
      const next = await fetchExecutionRecords(executionId, bin, offset);
      if (request !== sequence.current) return;
      if (next.execution_id !== executionId || next.bin !== bin || next.offset !== offset) {
        setError(t("evidence.stale"));
      } else {
        setPage(next);
      }
    } catch (failure) {
      if (request === sequence.current) {
        setError(t(/stale|conflict|requires_reimport/.test(String(failure)) ? "evidence.stale" : "evidence.error"));
      }
    } finally {
      if (request === sequence.current) setBusy(false);
    }
  }

  return <details className="m-3 rounded-lg border border-blue-100 p-3 text-xs">
    <summary className="cursor-pointer font-semibold text-blue-800">{t("evidence.title")}</summary>
    <div className="mt-3 flex gap-2">
      <select aria-label="Evidence bin" value={bin} onChange={event => selectBin(event.target.value)} className="rounded border p-2">
        {bins.map(value => <option key={value}>{value}</option>)}
      </select>
      <button disabled={busy || !bin} onClick={() => load()} className="rounded bg-blue-600 px-3 py-2 text-white">{t("evidence.load")}</button>
    </div>
    {error && <p role="alert" className="mt-2 text-rose-700">{error}</p>}
    {page && <div className="mt-3 space-y-2">
      <h4>{page.bin} · {t(("date." + page.date_basis) as TranslationKey)} · {t(("unit." + page.count_unit) as TranslationKey)} · {page.total_units} · {page.dataset_version_id}</h4>
      {page.groups.map(group => <article key={group.unit_id} className="rounded border p-2">
        <p>{t("evidence.group")}: {group.unit_id} · {t("evidence.date")}: {group.date}</p>
        {group.members.map(record => <details key={record.patent_number}>
          <summary>{record.patent_number} · {record.title}</summary>
          <p>{record.publication_date} · {record.kind_code} · {record.language}</p>
          <pre className="overflow-auto whitespace-pre-wrap break-all">{record.provenance}</pre>
        </details>)}
      </article>)}
      <button disabled={busy || page.offset === 0} onClick={() => load(Math.max(0, page.offset - page.limit))}>{t("evidence.previous")}</button>
      <button disabled={busy || page.offset + page.limit >= page.total_units} onClick={() => load(page.offset + page.limit)}>{t("evidence.next")}</button>
    </div>}
  </details>;
}
