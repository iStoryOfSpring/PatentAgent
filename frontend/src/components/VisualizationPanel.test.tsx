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

  it("keeps chart_html as a fallback for unknown result types", () => {
    const { container } = render(
      <VisualizationPanel toolName="legacy" result={{ result_type: "unknown" }} chartHtml="<div>legacy</div>" />,
    );
    expect(container.querySelector("iframe")).not.toBeNull();
  });
});

