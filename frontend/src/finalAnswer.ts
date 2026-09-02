import type { FollowupSuggestion } from "./types";
import { fieldLabel, formatDisplayValue } from "./uiLabels";
import { DEFAULT_LOCALE, translate, type Locale } from "./i18n";

export interface NormalizedAssistantContent {
  content: string;
  followupSuggestions: FollowupSuggestion[];
  followupQuestions: string[];
  normalizationMode: "native" | "local_repair" | "fallback";
}

const labelKeys: Record<string, string> = {
  answer: "final.coreConclusion", conclusion: "final.coreConclusion", summary: "final.coreConclusion",
  details: "final.details", findings: "final.findings", key_findings: "final.findings",
  key_points: "final.keyPoints", trend_summary: "final.trendSummary",
  methodology: "final.methodology", limitations: "final.limitations",
  warnings: "final.warnings", recommendations: "final.recommendations",
  year: "final.year", stage: "final.stage", theme: "final.theme",
  title: "final.title", name: "final.name", label: "final.label",
  representative_patents: "final.representativePatents", patents: "final.patents",
  applicants: "final.applicants", ipc: "final.ipc", ipc_codes: "final.ipcCodes",
};

const answerAliases = ["answer_markdown", "answer", "conclusion", "summary"];
const followupAliases = ["followup_suggestions", "follow_up_questions", "followup_questions"];
const evidenceAliases = ["evidence_refs", "evidence_references", "sources"];
const sectionOrder = [
  "details", "findings", "key_findings", "key_points", "trend_summary",
  "methodology", "limitations", "warnings", "recommendations",
];

function labelFor(key: string, locale: Locale): string {
  return labelKeys[key] ? translate(labelKeys[key], locale) : fieldLabel(key, locale);
}

function scalar(value: unknown, _key?: string, locale: Locale = DEFAULT_LOCALE): string {
  // Model, patent, and other result values are dynamic content. Only the
  // surrounding client-generated labels change with the selected locale.
  return formatDisplayValue(value, undefined, locale, false).trim();
}

function renderMapping(input: Record<string, unknown>, locale: Locale, level = 3): string {
  const values = { ...input };
  let heading = "";
  for (const identity of ["year", "stage", "title", "name", "label"]) {
    const value = values[identity];
    if (value !== undefined && value !== null && value !== "") {
      delete values[identity];
      const headingText = identity === "year"
        ? `${scalar(value, identity, locale)} ${translate("final.yearSuffix", locale)}`
        : scalar(value, identity, locale);
      heading = `${"#".repeat(level)} ${headingText}`;
      break;
    }
  }
  const lines = heading ? [heading] : [];
  for (const [key, value] of Object.entries(values)) {
    if (value === null || value === undefined || value === "") continue;
    if (Array.isArray(value) && value.length === 0) continue;
    const label = labelFor(key, locale);
    if (Array.isArray(value)) {
      lines.push(`**${label}：**`);
      for (const item of value) {
        lines.push(
          item && typeof item === "object" && !Array.isArray(item)
            ? renderMapping(item as Record<string, unknown>, locale, Math.min(level + 1, 6))
          : `- ${scalar(item, key, locale)}`,
        );
      }
    } else if (typeof value === "object") {
      lines.push(`**${label}：**`);
      lines.push(renderMapping(value as Record<string, unknown>, locale, Math.min(level + 1, 6)));
    } else {
      lines.push(`**${label}：** ${scalar(value, key, locale)}`);
    }
  }
  return lines.filter(Boolean).join("\n\n");
}

function renderSection(key: string, value: unknown, locale: Locale): string {
  const heading = `## ${labelFor(key, locale)}`;
  if (typeof value === "string") return `${heading}\n\n${value.trim()}`;
  if (Array.isArray(value)) {
    const body = value.map(item => (
      item && typeof item === "object" && !Array.isArray(item)
        ? renderMapping(item as Record<string, unknown>, locale)
        : `- ${scalar(item, key, locale)}`
    )).filter(Boolean).join("\n\n");
    return body ? `${heading}\n\n${body}` : "";
  }
  if (value && typeof value === "object") {
    return `${heading}\n\n${renderMapping(value as Record<string, unknown>, locale)}`;
  }
  return value === null || value === undefined ? "" : `${heading}\n\n${scalar(value, key, locale)}`;
}

function followupDefaults(text: string): Pick<FollowupSuggestion, "kind" | "requires_new_tools"> {
  if (["限制", "可信", "影响", "为什么", "原因"].some(word => text.includes(word))) {
    return { kind: "explain", requires_new_tools: false };
  }
  if (["方法", "算法", "口径", "如何计算"].some(word => text.includes(word))) {
    return { kind: "method", requires_new_tools: false };
  }
  return { kind: "new_analysis", requires_new_tools: true };
}

function normalizeFollowups(data: Record<string, unknown>): FollowupSuggestion[] {
  const raw = followupAliases.map(key => data[key]).find(Array.isArray);
  if (!Array.isArray(raw)) return [];
  const suggestions: FollowupSuggestion[] = [];
  for (const item of raw) {
    const object = item && typeof item === "object" && !Array.isArray(item)
      ? item as Record<string, unknown> : null;
    const text = typeof item === "string"
      ? item.trim() : String(object?.text || object?.question || "").trim();
    if (!text) continue;
    const defaults = followupDefaults(text);
    const kind = ["explain", "drilldown", "new_analysis", "method"].includes(String(object?.kind))
      ? object?.kind as FollowupSuggestion["kind"] : defaults.kind;
    suggestions.push({
      text,
      kind,
      requires_new_tools: typeof object?.requires_new_tools === "boolean"
        ? object.requires_new_tools : defaults.requires_new_tools,
      evidence_ref: typeof object?.evidence_ref === "string" ? object.evidence_ref : null,
    });
    if (suggestions.length === 3) break;
  }
  return suggestions;
}

function parseStructured(content: string): unknown | null {
  const trimmed = content.trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
  if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) return null;
  try { return JSON.parse(trimmed); } catch { return null; }
}

export function normalizeAssistantContent(content: string, locale: Locale = DEFAULT_LOCALE): NormalizedAssistantContent {
  const parsed = parseStructured(content);
  if (parsed === null) {
    return { content, followupSuggestions: [], followupQuestions: [], normalizationMode: "native" };
  }
  const data: Record<string, unknown> = Array.isArray(parsed)
    ? { details: parsed } : parsed && typeof parsed === "object"
      ? parsed as Record<string, unknown> : {};
  const answerKey = answerAliases.find(key => typeof data[key] === "string" && String(data[key]).trim());
  const sections: string[] = [];
  if (answerKey === "answer_markdown") sections.push(String(data[answerKey]).trim());
  else if (answerKey) sections.push(`## ${translate("final.coreConclusion", locale)}\n\n${String(data[answerKey]).trim()}`);

  const consumed = new Set([...answerAliases, ...followupAliases, ...evidenceAliases]);
  for (const key of sectionOrder) {
    if (key in data) {
      const section = renderSection(key, data[key], locale);
      if (section) sections.push(section);
      consumed.add(key);
    }
  }
  for (const [key, value] of Object.entries(data)) {
    if (consumed.has(key) || value === null || value === undefined || value === "") continue;
    const section = renderSection(key, value, locale);
    if (section) sections.push(section);
  }
  const suggestions = normalizeFollowups(data);
  if (!sections.length) {
    return {
      content: `## ${translate("final.analysisResult", locale)}\n\n${translate("final.invalidStructured", locale)}`,
      followupSuggestions: suggestions,
      followupQuestions: suggestions.map(item => item.text),
      normalizationMode: "fallback",
    };
  }
  return {
    content: sections.join("\n\n"),
    followupSuggestions: suggestions,
    followupQuestions: suggestions.map(item => item.text),
    normalizationMode: "local_repair",
  };
}
