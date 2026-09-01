// @vitest-environment jsdom
import { forwardRef, useImperativeHandle } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("./EChartCanvas", () => ({
  EChartCanvas: forwardRef(function MockChart(_props, ref) {
    useImperativeHandle(ref, () => ({ exportPng: vi.fn(), resize: vi.fn() }));
    return <div data-testid="native-echart">native chart</div>;
  }),
}));

import { VisualizationPanel } from "./VisualizationPanel";

const cases: Record<string, Record<string, unknown>> = {
  monthly_trend: { data: [{ year_month: "2024-01", count: 3 }] },
  yearly_trend: { data: [{ year: 2024, count: 3 }] },
  s_curve: { years: [2023, 2024], counts: [2, 3], cumulative: [2, 5] },
  ipc_matrix: { years: [2024], sections: ["H"], matrix: [[3]] },
  word_freq: { data: [{ word: "battery", count: 5 }] },
  burst_terms: { data: [{ term: "electrolyte", burst: 2, early_freq: 2, late_freq: 8 }] },
  yearly_keywords: { data: { 2024: [["battery", 5]] } },
  co_occurrence: { edges: [{ source: "A", target: "B", weight: 2 }] },
  country_distribution: { data: [{ country: "CN", count: 8 }] },
  dataset_summary: { total_patents: 8, year_start: 2023, year_end: 2024, ipc_sections: ["H"], top_applicants: [{ name: "A", count: 4 }] },
  roadmap: { data: { 2024: [{ patent_number: "P1", title: "Example", annual_themes: ["battery"] }] } },
  patent_search: { patents: [{ patent_number: "P1", title: "Example", relevance_score: .8 }] },
  patent_details: { patents: [{ patent_number: "P1", title: "Example", abstract: "Abstract" }] },
  tech_effect_matrix: { functions: ["cell"], effects: ["efficiency"], matrix: [[2]], gap_recommendations: [] },
  clustering: { patents_per_cluster: { 0: 3 }, cluster_titles: { 0: "Battery" }, cluster_keywords: { 0: ["cell"] }, silhouette_score: .4 },
  value_indicators: { score_label: "价值筛查分", data: [{ patent_number: "P1", score: 80 }] },
  competitor_evolution: { data: { evolution: [{ applicant: "A", years: [2023, 2024], ipc_entropy: [1, 1.2], dominant_ipc_share: [.6, .5], ipc_profile_cosine_shift: [0, .2], top_ipc: [["H01M"], ["H01M"]], total_patents: 8 }] } },
  entity_portfolio: { summary: "实体组合", data: [{ canonical_name: "A", record_count: 8 }] },
  concentration: { summary: "集中度", data: [{ hhi: .4, cr3: .8 }] },
  citation_network: { summary: "引证网络", data: [{ patent_number: "P1", pagerank: .5 }] },
  family_geography: { summary: "地域口径", data: [{ dimension: "priority_origin", values: [{ office_or_jurisdiction: "CN", count: 2 }] }] },
  search_strategy_audit: { summary: "检索审计", data: [{ version: 1, returned_count: 3 }] },
  legal_status: { summary: "法律状态", data: [{ status: "active", count: 2 }] },
  patent_monitor: { summary: "持续监测", data: [{ event_type: "new_publication", patent_number: "P1" }] },
  claim_elements: { data: [{ patent_number: "P1", kind_code: "A1", legal_status: "pending", claims: [{ claim_number: 1, is_independent: true, language: "en", elements: [{ element_number: 1, text: "a battery" }], product_feature_mapping_draft: [{ feature: "battery", matched_element_numbers: [1], match_method: "literal_substring" }] }] }] },
};

describe("VisualizationPanel registry", () => {
  for (const [resultType, payload] of Object.entries(cases)) {
    it(`renders ${resultType} from structured data without an iframe`, () => {
      const { container, unmount } = render(
        <VisualizationPanel
          toolName="test_tool"
          result={{ result_type: resultType, ...payload }}
          chartHtml={'<div id="legacy">legacy</div>'}
        />,
      );
      expect(screen.getByRole("button", { name: "图表" })).toBeTruthy();
      expect(container.querySelector("iframe")).toBeNull();
      unmount();
    });
  }

  it("does not execute chart_html for unknown result types", () => {
    const { container } = render(
      <VisualizationPanel toolName="legacy" result={{ result_type: "unknown" }} chartHtml="<div>legacy</div>" />,
    );
    expect(container.querySelector("iframe")).toBeNull();
    expect(screen.getByText("旧版网页图表（HTML）已禁用")).toBeTruthy();
  });

  it("marks claim analysis as a human-review draft", () => {
    render(<VisualizationPanel toolName="analyze_claim_elements" result={{ result_type: "claim_elements", ...cases.claim_elements }} />);
    expect(screen.getByText("人工复核草稿")).toBeTruthy();
    expect(screen.getByRole("checkbox")).toBeTruthy();
    expect(screen.getByText(/不构成侵权/)).toBeTruthy();
  });
});
