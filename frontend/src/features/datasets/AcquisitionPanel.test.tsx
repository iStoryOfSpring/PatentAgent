// @vitest-environment jsdom
import { cleanup,fireEvent,render,screen,waitFor } from "@testing-library/react";
import { afterEach,beforeEach,describe,expect,it,vi } from "vitest";
import { AcquisitionPanel } from "./AcquisitionPanel";
import * as api from "../../api";
vi.mock("../../api",()=>({fetchSources:vi.fn(),createAcquisition:vi.fn(),fetchAcquisition:vi.fn(),cancelAcquisition:vi.fn()}));
const request={source_id:"epo_ops",query:'ti="battery"',limit:100,name:"EPO OPS"};
const prepared={id:"acq1",state:"awaiting_confirmation",request,expires_at:"2026-10-15T12:00:00Z",confirmation_token:"one-time-token",outbound_host:"ops.epo.org"};
beforeEach(()=>{vi.clearAllMocks();Object.defineProperty(window,"localStorage",{configurable:true,value:{length:0,getItem:()=>null,setItem:vi.fn()}});vi.mocked(api.fetchSources).mockResolvedValue({sources:[]});});
afterEach(()=>cleanup());
describe("acquisition review",()=>{
  it("requires an explicit second action using exactly the reviewed request and memory token",async()=>{
    vi.mocked(api.createAcquisition).mockResolvedValueOnce({acquisition:prepared}).mockResolvedValueOnce({acquisition:{...prepared,state:"credentials_required",confirmation_token:undefined}});
    const changed=vi.fn();render(<AcquisitionPanel onChanged={changed} onError={vi.fn()}/>);
    fireEvent.click(screen.getByText("查看采集确认摘要"));
    await screen.findByText("确认向 EPO 发送查询");
    expect(api.createAcquisition).toHaveBeenCalledTimes(1);
    expect(screen.getByText("https://ops.epo.org")).toBeTruthy();
    expect(document.body.textContent).not.toContain("one-time-token");
    expect(window.localStorage.length).toBe(0);
    fireEvent.click(screen.getByText("确认向 EPO 发送查询"));
    await screen.findByText(/缺少后端 EPO OPS 凭据/);
    expect(api.createAcquisition).toHaveBeenLastCalledWith({...request,acquisition_id:"acq1",confirmation_token:"one-time-token"});
    expect(changed).toHaveBeenCalledTimes(1);
  });
  it("editing the query invalidates the visible approval and cancel prevents confirmation",async()=>{
    vi.mocked(api.createAcquisition).mockResolvedValue({acquisition:prepared});
    vi.mocked(api.cancelAcquisition).mockResolvedValue({acquisition:{...prepared,state:"cancelled",confirmation_token:undefined}});
    render(<AcquisitionPanel onChanged={vi.fn()} onError={vi.fn()}/>);
    fireEvent.click(screen.getByText("查看采集确认摘要"));await screen.findByText("确认向 EPO 发送查询");
    fireEvent.change(screen.getByLabelText("将外发的 EPO CQL 查询"),{target:{value:"changed query"}});
    expect(screen.queryByText("确认向 EPO 发送查询")).toBeNull();
    fireEvent.click(screen.getByText("取消采集"));await screen.findByText(/已取消/);
    expect(api.createAcquisition).toHaveBeenCalledTimes(1);
  });
  it("partial acquisition displays no publication claim",async()=>{
    vi.mocked(api.createAcquisition).mockResolvedValue({acquisition:{...prepared,state:"partial",confirmation_token:undefined,matched_set_complete:false}});
    render(<AcquisitionPanel onChanged={vi.fn()} onError={vi.fn()}/>);
    fireEvent.click(screen.getByText("查看采集确认摘要"));
    await screen.findByText(/返回集合不完整：未发布数据集/);
    expect(screen.queryByText(/返回集合完整；/)).toBeNull();
  });
});
