// @vitest-environment jsdom
import { cleanup,fireEvent,render,screen } from "@testing-library/react";
import { afterEach,beforeEach,describe,expect,it,vi } from "vitest";
import { ExecutionEvidence } from "./ExecutionEvidence";
import * as api from "../api";
vi.mock("../api",()=>({fetchExecutionRecords:vi.fn()}));
const page={execution_id:"exec1",bin:"2018",date_basis:"filing",count_unit:"applications",total_units:26,offset:0,limit:25,dataset_version_id:"version1",groups:[{unit_id:"USAPP1",date:"2018-01-01",publication_numbers:["US1A1","US1B2"],members:[{patent_number:"US1A1",title:"<img src=x>",language:"en",kind_code:"A1",publication_date:"2020-01-01",dataset_version_id:"version1",provenance:"EPO OPS"}]}]};
beforeEach(()=>{vi.clearAllMocks();Object.defineProperty(window,"localStorage",{configurable:true,value:{length:0,getItem:()=>null,setItem:vi.fn()}});});afterEach(()=>cleanup());
describe("persisted execution evidence",()=>{
  it("paginates only by registered bin and shows counted group members",async()=>{
    vi.mocked(api.fetchExecutionRecords).mockResolvedValueOnce(page).mockResolvedValueOnce({...page,offset:25,groups:[{...page.groups[0],unit_id:"USAPP26"}]});
    render(<ExecutionEvidence executionId="exec1" bins={["2018","2019"]}/>);
    fireEvent.click(screen.getByText("查看此分组证据"));await screen.findByText(/USAPP1/);
    expect(screen.getByText(/申请日期 · 申请数/)).toBeTruthy();
    expect(document.querySelector("img")).toBeNull();
    fireEvent.click(screen.getByText("下一页"));await screen.findByText(/USAPP26/);
    expect(api.fetchExecutionRecords).toHaveBeenLastCalledWith("exec1","2018",25);
  });
  it("rejects stale results visibly without falling back to all records",async()=>{
    vi.mocked(api.fetchExecutionRecords).mockRejectedValue(new Error("requires_reimport: conflict"));
    render(<ExecutionEvidence executionId="exec1" bins={["2018"]}/>);
    fireEvent.click(screen.getByText("查看此分组证据"));
    expect((await screen.findByRole("alert")).textContent).toContain("证据或数据版本已失效，请重新分析。");
    expect(api.fetchExecutionRecords).toHaveBeenCalledTimes(1);
  });
});
