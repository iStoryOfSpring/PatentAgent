// Deprecated compatibility renderer. Scripts and external-window execution are disabled.
import { useI18n } from "../i18n";

export function ChartFrame({ html, height }: { html: string; height?: number }) {
  const { t } = useI18n();
  const widths = [...html.matchAll(/width:\s*(\d+)px/gi)].map(match => Number(match[1]));
  const heights = [...html.matchAll(/height:\s*(\d+)px/gi)].map(match => Number(match[1]));
  const naturalWidth = Math.max(720, ...widths, 0);
  const naturalHeight = height || Math.min(900, Math.max(420, heights.reduce((sum, value) => sum + value, 0) || 520));
  const documentHtml = html.includes("</head>") ? html.replace(
    "</head>",
    `<style>html,body{margin:0;padding:0;background:#fff;min-height:100%;}body{overflow:auto;}table{max-width:100%;}</style></head>`,
  ) : html;
  return (
    <div className="p-3">
      <div className="max-w-full overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <iframe
          srcDoc={documentHtml}
          style={{ width: `${naturalWidth}px`, minWidth: `${naturalWidth}px`, height: naturalHeight, border: "none" }}
          sandbox=""
          title={t("visual.oldChartTitle")}
          className="block bg-white"
        />
      </div>
      <p className="mt-1 text-[10px] text-slate-400">{t("visual.oldChartDescription")}</p>
    </div>
  );
}
