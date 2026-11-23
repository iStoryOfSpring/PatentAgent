// @vitest-environment jsdom
import { act,cleanup,fireEvent,render,screen } from "@testing-library/react";
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
  it("offers the publication link inside the counted record alongside local provenance", async () => {
    const group = page.groups[0];
    const record = { ...group.members[0], patent_number: "WO 2020263523 A1", title: "Counted publication" };
    vi.mocked(api.fetchExecutionRecords).mockResolvedValueOnce({
      ...page,
      groups: [{ ...group, publication_numbers: [record.patent_number], members: [record] }],
    });

    render(<ExecutionEvidence executionId="exec1" bins={["2018"]} />);
    fireEvent.click(screen.getByText("按统计分组查看原始文献证据"));
    fireEvent.click(screen.getByText("查看此分组证据"));
    fireEvent.click(await screen.findByText(/Counted publication/));

    const link = screen.getByRole("link", { name: "在 Google Patents 查看 WO2020263523A1（新标签页）" });
    expect(link.getAttribute("href")).toBe("https://patents.google.com/patent/WO2020263523A1");
    expect(link.closest("summary")).toBeNull();
    expect(screen.getByText("EPO OPS")).toBeTruthy();
    expect(api.fetchExecutionRecords).toHaveBeenCalledExactlyOnceWith("exec1", "2018", 0);
  });

  it("rejects stale results visibly without falling back to all records",async()=>{
    vi.mocked(api.fetchExecutionRecords).mockRejectedValue(new Error("requires_reimport: conflict"));
    render(<ExecutionEvidence executionId="exec1" bins={["2018"]}/>);
    fireEvent.click(screen.getByText("查看此分组证据"));
    expect((await screen.findByRole("alert")).textContent).toContain("证据或数据版本已失效，请重新分析。");
    expect(api.fetchExecutionRecords).toHaveBeenCalledTimes(1);
  });
});

it.each(["resolve", "reject"])("ignores a late %s after selecting another year", async outcome => {
  let finish!: () => void;
  vi.mocked(api.fetchExecutionRecords).mockImplementationOnce(() => new Promise((resolve, reject) => {
    finish = () => outcome === "resolve" ? resolve(page) : reject(new Error("stale"));
  }));
  render(<ExecutionEvidence executionId="exec1" bins={["2018", "2019"]}/>);
  fireEvent.click(screen.getByText("查看此分组证据"));
  fireEvent.change(screen.getByLabelText("Evidence bin"), {target: {value: "2019"}});
  await act(async () => finish());
  expect(screen.queryByText(/USAPP1/)).toBeNull();
  expect(screen.queryByRole("alert")).toBeNull();
  expect((screen.getByText("查看此分组证据") as HTMLButtonElement).disabled).toBe(false);
});

it("invalidates pending work on execution change and disables empty bins", async () => {
  let finish!: () => void;
  vi.mocked(api.fetchExecutionRecords).mockImplementationOnce(() => new Promise(resolve => {
    finish = () => resolve(page);
  }));
  const view = render(<ExecutionEvidence executionId="exec1" bins={["2018"]}/>);
  fireEvent.click(screen.getByText("查看此分组证据"));
  view.rerender(<ExecutionEvidence executionId="exec2" bins={[]}/>);
  await act(async () => finish());
  expect(screen.queryByText(/USAPP1/)).toBeNull();
  expect((screen.getByText("查看此分组证据") as HTMLButtonElement).disabled).toBe(true);
});

it("retains the current page on pagination failure and rejects mismatched responses", async () => {
  vi.mocked(api.fetchExecutionRecords).mockResolvedValueOnce(page)
    .mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({...page, execution_id:"other"});
  render(<ExecutionEvidence executionId="exec1" bins={["2018"]}/>);
  fireEvent.click(screen.getByText("查看此分组证据"));
  await screen.findByText(/USAPP1/);
  fireEvent.click(screen.getByText("下一页"));
  await screen.findByRole("alert");
  expect(screen.getByText(/USAPP1/)).toBeTruthy();
  fireEvent.click(screen.getByText("下一页"));
  expect((await screen.findByRole("alert")).textContent).toContain("失效");
});
