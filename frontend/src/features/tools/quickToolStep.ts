import type { ToolResult,ToolStep } from "../../types";

/** Keep the persisted execution identity when projecting a quick result into chat. */
export function quickToolStep(result:ToolResult,toolName:string,params:Record<string,unknown>,id:string):ToolStep {
  return {id,execution_id:typeof result.result_metadata?.execution_id==="string"?result.result_metadata.execution_id:undefined,
    tool:toolName,status:"completed",chart_html:result.chart_html,summary:result.summary,methodology:result.methodology,
    data_quality:result.data_quality,warnings:result.warnings,
    parameters:(result.result_metadata?.parameters || params) as Record<string,unknown>,result:result as Record<string,unknown>};
}
