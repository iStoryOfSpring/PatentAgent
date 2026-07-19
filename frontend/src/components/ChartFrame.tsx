// 旧版 chart_html 兼容渲染器；已知结果优先使用原生结构化组件。
export function ChartFrame({ html, height }: { html: string; height?: number }) {
  const widths = [...html.matchAll(/width:\s*(\d+)px/gi)].map(match => Number(match[1]));
  const heights = [...html.matchAll(/height:\s*(\d+)px/gi)].map(match => Number(match[1]));
  const naturalWidth = Math.max(720, ...widths, 0);
  const naturalHeight = height || Math.min(900, Math.max(420, heights.reduce((sum, value) => sum + value, 0) || 520));
  const documentHtml = html.includes("</head>") ? html.replace(
    "</head>",
    `<style>html,body{margin:0;padding:0;background:#fff;min-height:100%;}body{overflow:auto;}table{max-width:100%;}</style></head>`,
  ) : html;
  const handleOpenNewWindow = () => {
    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank", "noopener,noreferrer");
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
  };

  return (
    <div className="p-3">
      <div className="max-w-full overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <iframe
          srcDoc={documentHtml}
          style={{ width: `${naturalWidth}px`, minWidth: `${naturalWidth}px`, height: naturalHeight, border: "none" }}
          sandbox="allow-scripts"
          title="PatentAgent 旧版分析图表"
          className="block bg-white"
        />
      </div>
      <button
        onClick={handleOpenNewWindow}
        className="mt-1 text-[10px] text-slate-400 hover:text-blue-500 transition-colors"
      >
        ↗ 在新窗口查看旧版图表
      </button>
    </div>
  );
}
