// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { DatasetsPage } from "./DatasetsPage";
import * as api from "../../api";

vi.mock("../../api", () => ({ uploadDataset:vi.fn(), fetchImport:vi.fn() }));
vi.mock("./AcquisitionPanel", () => ({ AcquisitionPanel:() => null }));
afterEach(cleanup);

it("shows restart recovery and enables reupload after the terminal response", async () => {
  vi.mocked(api.uploadDataset).mockResolvedValue({import_id:"job", dataset_id:"dataset", files:["demo.jsonl"], status:"queued"});
  vi.mocked(api.fetchImport).mockResolvedValue({id:"job", status:"failed", error_category:"import_interrupted",
    error:"导入因服务重启中断，请重新上传", created_at:"", updated_at:"", metrics:{progress:100}});
  const changed = vi.fn();
  const view = render(<DatasetsPage datasets={[]} activeSessionId="session" onChanged={changed} onError={vi.fn()}/>);
  const button = screen.getByRole("button", {name:"上传并导入"}) as HTMLButtonElement;
  fireEvent.change(view.container.querySelector('input[type="file"]')!, {target:{files:[new File(["{}"], "demo.jsonl")]}});
  fireEvent.click(button);
  expect(button.disabled).toBe(true);
  await screen.findByText("导入因服务重启中断，请重新上传", {}, {timeout:3000});
  expect(button.disabled).toBe(false);
  expect(changed).toHaveBeenCalledOnce();
  expect(api.fetchImport).toHaveBeenCalledOnce();
});
