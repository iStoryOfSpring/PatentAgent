"""Local, deterministic follow-up reviews for annual trends and matrix candidates."""
from datetime import date
import re

import pandas as pd

from engine.trend import select_trend_population
from models.analysis_results import GenericAnalysisResult
from tools.base import Tool, tool_registry


MAX_TERMS = 12
MAX_LENGTH = 100
LIMIT = {"type": "integer", "minimum": 1, "maximum": 25, "default": 8}
WORDS = {"type": "array", "maxItems": MAX_TERMS, "items": {"type": "string", "maxLength": MAX_LENGTH}}
BILINGUAL = (
    ("near infrared", "near-infrared", "NIR", "近红外"),
    ("sorting", "separator", "separation", "分选", "分离"),
    ("textile", "fabric", "纺织", "织物"),
    ("recycling", "recovery", "回收", "再生利用"),
)


def direction(values):
    if len(values) < 2 or not values[0] or not values[-1]:
        return "incomparable"
    return "increase" if values[-1] > values[0] else "decrease" if values[-1] < values[0] else "flat"


class TrendReview(Tool):
    name = "audit_trend_robustness"
    description = "比较指定日期轴上的年度公开文献数、申请数、真实同族数和去尾年方向。"
    parameters = {
        "date_basis": {"type":"string", "enum":["publication","filing","priority","grant"], "default":"publication"},
        "year_start":{"type":"integer", "minimum":1, "maximum":9999},
        "year_end":{"type":"integer", "minimum":1, "maximum":9999},
        "applicant_filter":{"type":"string", "maxLength":100}, "ipc_filter":WORDS, "example_limit":LIMIT,
    }
    required_fields = ("patent_number",)
    methodology = "年度归属沿用原趋势的最早有效日期。缺标识或端点无观察不作增减比较。"

    async def execute(self, storage, date_basis="publication", year_start=None, year_end=None,
                      applicant_filter=None, ipc_filter=None, example_limit=8):
        _terms(ipc_filter or [])
        if applicant_filter is not None:
            _terms([applicant_filter])
        options = dict(date_basis=date_basis, chart_type="yearly", year_start=year_start, year_end=year_end,
                       applicant_filter=applicant_filter, ipc_filter=ipc_filter)
        counted = {}
        for unit in ("publications", "applications", "families"):
            _, members, meta = select_trend_population(storage, count_unit=unit, **options)
            counted[unit] = members, meta
        observed = sorted(int(year) for year in counted["publications"][0])
        start = year_start or (observed[0] if observed else None)
        end = year_end or (observed[-1] if observed else None)
        if start and end and end - start > 500:
            raise ValueError("请选择不超过 501 年的窗口")
        years = list(range(start, end + 1)) if start and end else []
        population = storage.query(ipc_filter=ipc_filter, applicant_filter=applicant_filter)
        column = counted["publications"][1]["date_semantics"]
        dates = pd.to_datetime(population.get(column, pd.Series(index=population.index, dtype=str)), errors="coerce")
        publication_year = dict(zip(population["patent_number"].astype(str), dates.dt.year))
        rows, examples = [], []
        example_total = 0
        for unit, (members, meta) in counted.items():
            counts = [len(members.get(str(year), [])) for year in years]
            change = direction(counts)
            rows.append(dict(unit=unit, annual_counts=counts, direction=change,
                             endpoint_delta=counts[-1]-counts[0] if change != "incomparable" else None,
                             sustained_growth=all(a < b for a,b in zip(counts, counts[1:])) if change != "incomparable" else None,
                             without_tail_direction=direction(counts[:-1]), missing_ids=meta["missing_identity_records"],
                             missing_dates=meta["missing_date_records"], coverage_population=len(population)))
            if unit == "publications":
                continue
            for year, groups in sorted(members.items()):
                for group in groups:
                    numbers = group["publication_numbers"]
                    if len(numbers) < 2:
                        continue
                    example_total += 1
                    if len(examples) < example_limit:
                        examples.append({"unit":unit, "year":int(year), "unit_id":group["unit_id"],
                                         "publication_numbers":numbers[:25], "publication_count":len(numbers),
                                         "member_list_truncated":len(numbers)>25,
                                         "cross_year":any(pd.notna(publication_year.get(n)) and publication_year[n]!=int(year) for n in numbers)})
        for unit, field in (("applications","application_number"), ("families","family_id")):
            identities = population.get(field, pd.Series("", index=population.index)).fillna("").astype(str).str.strip()
            if field == "application_number":
                from engine.adapters.common import normalized_application_number
                identities = identities.map(normalized_application_number)
            missing = population.loc[identities.eq("") & dates.dt.year.isin(years), "patent_number"]
            example_total += len(missing)
            for number in sorted(missing.astype(str))[:max(0,example_limit-len(examples))]:
                examples.append({"unit":unit, "reason":"missing_identity", "year":int(publication_year[number]),
                                 "publication_numbers":[number], "publication_count":1})
        try:
            cutoff = date.fromisoformat(str(storage.audit().get("data_as_of", ""))[:10])
        except ValueError:
            cutoff = None
        tail = "unknown" if not cutoff or not years else "partial" if cutoff < date(years[-1],12,31) else "through_year_end"
        valid = {row["direction"] for row in rows} - {"incomparable"}
        verdict = "divergent" if len(valid)>1 else "insufficient" if any(row["direction"]=="incomparable" for row in rows) else "consistent"
        return GenericAnalysisResult(result_type="trend_robustness", data=rows, years=years, date_basis=date_basis,
            verdict=verdict, cutoff=cutoff.isoformat() if cutoff else "", tail_coverage=tail, examples=examples,
            example_total=example_total, examples_truncated=example_total>len(examples),
            summary=f"比较 {len(years)} 个年度的三种统计口径，示例来自当前范围。",
            warnings=["计数方向只描述当前数据范围。缺标识、无端点观察和不完整尾年限制结论。"])


def _terms(items):
    if not isinstance(items, list) or len(items)>MAX_TERMS:
        raise ValueError("扩展词或分类列表最多 12 项")
    if any(not isinstance(word,str) or not word.strip() or len(word)>MAX_LENGTH for word in items):
        raise ValueError("每个词必须为 1–100 个字符")
    return [word.strip() for word in items]


def _axis(term, synonyms):
    base = _terms([term])[0]
    entries = {base.casefold():(base, "original")}
    for word in _terms(synonyms):
        entries.setdefault(word.casefold(), (word,"user"))
    for group in BILINGUAL:
        if set(entries).intersection(word.casefold() for word in group):
            for word in group:
                entries.setdefault(word.casefold(), (word,"dictionary"))
    return list(entries.values())


def _patterns(entries):
    patterns = []
    for term, source in entries:
        left = r"(?<![a-zA-Z0-9_])" if term[0].isascii() and term[0].isalnum() else ""
        right = r"(?![a-zA-Z0-9_])" if term[-1].isascii() and term[-1].isalnum() else ""
        patterns.append((term, source, re.compile(left+re.escape(term)+right,re.I)))
    return patterns


def _hits(patterns, fields):
    hits = []
    for term, origin, pattern in patterns:
        for field, text in fields.items():
            match = pattern.search(text)
            if match:
                start, end = max(0,match.start()-35), min(len(text),match.end()+35)
                hits.append(dict(term=term, origin=origin, field=field, start=start, end=end, snippet=text[start:end]))
                break
    return hits


def _text(value):
    if value is None or not isinstance(value, (list, tuple, dict)) and pd.isna(value):
        return ""
    return str(value)


def _codes(value):
    if isinstance(value, (list,tuple)):
        return [str(code).strip() for code in value if code]
    return [word.strip() for word in re.split(r"[;,|]", _text(value)) if word.strip()]


class GapReview(Tool):
    name = "search_gap_counterevidence"
    description = "在当前完整范围分轮查找技术手段和用途的原文反证，列出同义扩展、分类线索和逐件复核成本。"
    parameters = {"technology":{"type":"string","required":True,"maxLength":100},
                  "effect":{"type":"string","required":True,"maxLength":100},
                  "technology_terms":WORDS, "effect_terms":WORDS, "ipc_prefixes":WORDS,
                  "cpc_prefixes":WORDS, "example_limit":LIMIT}
    required_fields = ("patent_number",)
    methodology = "按同文献标题或摘要双轴命中、双语扩展双轴命中、分类与至少单轴命中分轮复核。"

    async def execute(self, storage, technology, effect, technology_terms=None, effect_terms=None,
                      ipc_prefixes=None, cpc_prefixes=None, example_limit=8):
        axes = [_axis(technology, technology_terms or []), _axis(effect, effect_terms or [])]
        patterns = [_patterns(axis) for axis in axes]
        prefixes = {field:[term.replace(" ","").upper() for term in _terms(values or [])]
                    for field,values in (("ipc", ipc_prefixes), ("cpc_codes", cpc_prefixes))}
        rounds = [dict(stage=stage, hits=0, new=0, overlap=0, missing_family=0, candidates=[])
                  for stage in ("original","expanded","classification")]
        families = [set() for _ in rounds]
        total_missing = unique_hits = missing_title = missing_abstract = 0
        frame = storage.get_columns(["patent_number","family_id","title","abstract","ipc","cpc_codes"])
        frame = frame.sort_values("patent_number",kind="stable").drop_duplicates("patent_number")
        for row in frame.itertuples(index=False):
            fields = {field:_text(getattr(row,field,"")) for field in ("title","abstract")}
            missing_title += not fields["title"]
            missing_abstract += not fields["abstract"]
            left, right = [_hits(axis, fields) for axis in patterns]
            matched_codes = [{"scheme":"IPC" if field=="ipc" else "CPC", "code":code}
                             for field, prefix in prefixes.items() for code in _codes(getattr(row,field,""))
                             if prefix and code.replace(" ","").upper().startswith(tuple(prefix))]
            match = [any(h["origin"]=="original" for h in left) and any(h["origin"]=="original" for h in right),
                     bool(left and right), bool(matched_codes and (left or right))]
            if not any(match):
                continue
            unique_hits += 1
            family = _text(getattr(row,"family_id","")).strip()
            total_missing += not family
            for index, hit in enumerate(match):
                if not hit:
                    continue
                result = rounds[index]
                result["hits"] += 1
                overlap = any(match[:index])
                result["overlap"] += overlap
                result["new"] += not overlap
                result["missing_family"] += not family
                if family:
                    families[index].add(family)
                if not overlap and len(result["candidates"]) == example_limit:
                    # Prefer incremental evidence when alphabetical overlaps fill the display.
                    if not result["candidates"][-1]["new"]:
                        result["candidates"].pop()
                if len(result["candidates"]) < example_limit:
                    result["candidates"].append(dict(publication=_text(row.patent_number), family=family,
                        technology_hits=left[:1] if index==0 else left, effect_hits=right[:1] if index==0 else right,
                        classifications=matched_codes if index==2 else [], level="text_both" if left and right else "single_axis_lead",
                        new=not overlap))
                    result["candidates"].sort(key=lambda item: not item["new"])
        prior = set()
        for result, group in zip(rounds, families):
            result.update(known_families=len(group), new_families=len(group-prior),
                          truncated=result["hits"]>len(result["candidates"]))
            prior.update(group)
        return GenericAnalysisResult(result_type="gap_counterevidence", data=rounds,
            technology_terms=axes[0], effect_terms=axes[1], class_prefixes=prefixes, reviewed_records=len(frame),
            unique_hits=unique_hits, known_families=len(prior), missing_family=total_missing,
            missing_title=missing_title, missing_abstract=missing_abstract, has_expansions=any(len(axis)>1 for axis in axes),
            summary=f"检索 {len(frame)} 件，去重后 {unique_hits} 件候选需复核。",
            warnings=["零命中受语料覆盖和检索式限制，不能据此判断市场空白、新颖性或自由实施。"])


tool_registry.register(TrendReview())
tool_registry.register(GapReview())
