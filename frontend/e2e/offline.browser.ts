import { expect, test } from "@playwright/test";
import path from "node:path";

test("offline upload, session binding and filing-year application evidence", async ({page, context}) => {
  const origin = new URL(process.env.PATENTAGENT_E2E_URL!).origin;
  const unexpected: string[] = [];
  await context.route("**/*", route => {
    const url = new URL(route.request().url());
    if (url.origin === origin || ["data:", "blob:"].includes(url.protocol)) return route.continue();
    unexpected.push(url.origin);
    return route.abort();
  });
  page.on("dialog", dialog => dialog.accept());
  await page.goto("/datasets");
  await page.locator('input[type="file"]').setInputFiles(path.resolve("../samples/offline/trend.jsonl"));
  await page.getByLabel("数据集名称").fill("离线趋势样例");
  const completed = page.waitForResponse(async response => {
    if (!response.url().includes("/api/imports/") || !response.ok()) return false;
    return (await response.json()).import.status === "completed";
  });
  await page.getByRole("button", {name:"上传并导入"}).click();
  const version = (await (await completed).json()).import.dataset_version_id;
  expect(version).toMatch(/^version_/);
  await page.goto("/chat/new");
  const created = page.waitForResponse(r => r.url().endsWith("/api/sessions") && r.request().method() === "POST" && r.ok());
  await page.getByRole("button", {name:"新会话", exact:true}).click();
  await created;
  await expect(page).toHaveURL(/\/chat\/(?!new)[^/]+$/);
  await page.goto("/datasets");
  const dataset = page.getByRole("article").filter({has: page.getByRole("heading", {name:"离线趋势样例"})});
  await expect(dataset).toBeVisible();
  const bind = dataset.getByRole("button", {name:"绑定会话", exact:true});
  if (await bind.isVisible()) await bind.click();
  await expect(dataset.getByRole("button", {name:"已绑定", exact:true})).toBeDisabled();
  await page.goto("/capabilities");
  await page.locator("aside").getByTitle("公开趋势", {exact:true}).click();
  await page.getByLabel(/^统计日期/).selectOption("filing");
  await page.getByLabel(/^计数单位/).selectOption("applications");
  await page.getByLabel(/^图表粒度/).selectOption("yearly");
  await page.getByRole("button", {name:"执行", exact:true}).click();
  await page.getByRole("button", {name:"回到聊天页面"}).click();
  await expect(page.getByRole("figure", {name:"申请日期 · 申请数"})).toBeVisible();
  await page.getByText("按统计分组查看原始文献证据").click();
  const select = page.getByLabel("Evidence bin");
  await expect(select.locator("option")).toHaveText(["2018", "2019"]);
  for (const [year, publications] of [
    ["2018", ["US-900000001-A1", "US-900000001-B2"]], ["2019", ["US-900000002-A1"]],
  ] as const) {
    await select.selectOption(year);
    await page.getByRole("button", {name:"查看此分组证据"}).click();
    const heading = page.getByRole("heading", {name:`${year} · 申请日期 · 申请数 · 1 · ${version}`});
    await expect(heading).toBeVisible();
    const members = heading.locator("..").locator("article summary");
    await expect(members).toHaveCount(publications.length);
    for (const publication of publications) await expect(members.filter({hasText:publication})).toHaveCount(1);
  }
  expect(unexpected).toEqual([]);
});
