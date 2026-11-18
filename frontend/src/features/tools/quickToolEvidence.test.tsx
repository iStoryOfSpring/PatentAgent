// @vitest-environment jsdom
import { forwardRef,useImperativeHandle } from "react";
import { cleanup,render,screen } from "@testing-library/react";
import { afterEach,expect,it,vi } from "vitest";
import { quickToolStep } from "./quickToolStep";
import { messagesFromSession } from "../sessions/restoreMessages";
import { ToolStepCard } from "../../components/ToolStepCard";
import type { ToolResult,SessionDetail } from "../../types";
vi.mock("../../components/EChartCanvas",()=>({EChartCanvas:forwardRef(function MockChart(props:{option:Record<string,unknown>},ref){useImperativeHandle(ref,()=>({exportPng:vi.fn()}));return <div>{String((props.option.title as Record<string,unknown>)?.text)}</div>;})}));
afterEach(cleanup);
const result={result_type:"yearly_trend",chart_html:null,summary:"30 applications",methodology:"count real application identities",data_quality:{},warnings:[],data:[{year:2018,count:30}],result_metadata:{execution_id:"quick_saved_exec",date_basis:"filing",count_unit:"applications",evidence_bins:{"2018":{unit_count:30,membership_sha256:"hash"}},evidence_selector_version:"trend-units-v1"}} as ToolResult;
it("immediate quick tool chat preserves execution identity and renders evidence with selected count labels",async()=>{
  const step=quickToolStep(result,"analyze_patent_trend",{},"step1");
  render(<ToolStepCard step={step}/>);
  expect(await screen.findByText("按统计分组查看原始文献证据")).toBeTruthy();
  expect(await screen.findByText("申请日期 · 申请数")).toBeTruthy();
  expect(step.execution_id).toBe("quick_saved_exec");
});
it("restored persisted executions expose the same evidence entry without metadata execution id",async()=>{
  const detail={session:{id:"s"},turns:[{id:"turn1",status:"completed"}],messages:[{id:1,turn_id:"turn1",role:"assistant",content:"done"}],tool_executions:[{id:"persisted_exec",turn_id:"turn1",tool_name:"analyze_patent_trend",status:"completed",parameters:{},result:{...result,result_metadata:{...result.result_metadata,execution_id:undefined}}}]} as unknown as SessionDetail;
  const step=messagesFromSession(detail)[0].steps![0];
  render(<ToolStepCard step={step}/>);
  expect(await screen.findByText("按统计分组查看原始文献证据")).toBeTruthy();
  expect(step.execution_id).toBe("persisted_exec");
});
