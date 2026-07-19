# 16 工具算法证据矩阵

> 由 `knowledge/tool_evidence.json` 自动生成；登记版本 `2026.07.19`。请勿手工维护本表。

| 工具 | algorithm_id / 版本 | 证据等级 | 公式或实现 | 字段门槛 | 来源 | 禁止结论 |
|---|---|---|---|---|---|---|
| `analyze_patent_trend` | `publication_count_trend` / `2.0` | `descriptive_statistic` | count(records) grouped by publication year/month | publication_date>=90% | — | application trend; technology decline; technology lifecycle |
| `analyze_lifecycle` | `publication_growth_summary` / `2.0` | `engineering_screening` | annual publication count, cumulative count, year-over-year change | publication_date>=90% | — | S-curve lifecycle stage; decline stage; technology maturity |
| `analyze_ipc_distribution` | `ipc_publication_matrix` / `2.0` | `descriptive_statistic` | count all normalized multi-value IPC assignments by year and selected granularity | publication_date>=90%; ipc>=90% | — | exclusive technology share |
| `generate_wordcloud` | `derwent_phrase_frequency` / `2.0` | `engineering_screening` | document-aware cleaned phrase frequency | title>=80% | Tseng et al. 2007, Information Processing & Management 43, 1216-1247 | paper-exact text mining pipeline; technology value |
| `analyze_burst_terms` | `recent_document_frequency_growth` / `2.0` | `engineering_screening` | smoothed recent-vs-history document-frequency ratio with minimum support | publication_date>=90%; title>=80%; abstract>=80% | — | Kleinberg burst detection; validated emerging technology forecast |
| `analyze_yearly_keywords` | `yearly_phrase_frequency` / `2.0` | `engineering_screening` | cleaned phrase document frequency by publication year | publication_date>=90%; title>=80% | — | causal technology migration |
| `analyze_co_network` | `co_applicant_network` / `2.0` | `descriptive_statistic` | undirected edge for each pair of co-applicants on the same record | applicants>=90% | — | alliance; technology transfer; co-invention |
| `analyze_country_distribution` | `primary_publication_office_count` / `2.0` | `descriptive_statistic` | country prefix of primary PN | patent_number>=90% | — | family market coverage; market attractiveness |
| `analyze_tech_roadmap` | `annual_theme_timeline` / `2.0` | `engineering_screening` | annual themes and representative records; citation paths only when resolved | publication_date>=90%; title>=80%; patent_number>=90% | — | complete invention genealogy; causal technology route |
| `get_dataset_summary` | `dataset_field_audit` / `2.0` | `descriptive_statistic` | record counts, field coverage, batch manifest and network coverage | — | — | — |
| `search_patents` | `tfidf_cosine_retrieval` / `2.0` | `engineering_screening` | cosine similarity in word/phrase TF-IDF space | title>=80%; abstract>=80%; patent_number>=90% | — | vector embedding; legal novelty search; exhaustive prior-art search |
| `read_patent_details` | `structured_record_lookup` / `2.0` | `descriptive_statistic` | exact lookup of parsed source fields | patent_number>=90% | — | full specification; complete claims; legal status conclusion |
| `analyze_tech_matrix` | `derwent_abstract_proxy_te_matrix` / `2.0` | `engineering_screening` | co-occurrence of technology phrases from NOVELTY with use/effect phrases from USE/ADVANTAGE | abstract>=80% | Tseng et al. 2007, Information Processing & Management 43, 1216-1247 | blue ocean; validated white space; paper-exact function matrix |
| `analyze_clustering` | `tfidf_kmeans_cc05_labels` / `2.0` | `paper_adapted` | K-means in TF-IDF space; silhouette selects k; CC0.5 labels require cluster DF > 50% and document-level phi correlation | title>=80%; abstract>=80% | Tseng et al. 2007, Information Processing & Management 43, 1216-1247 | complete Tseng multi-stage pipeline; ground-truth technology taxonomy |
| `analyze_patent_valuation` | `patent_family_citation_screening` / `3.0` | `paper_adapted` | robust percentile screening; SS diagnostic = RO + BC only when family/network gates pass | patent_number>=90%; publication_date>=90%; ipc>=90% | von Wartburg, Teichert & Rost 2005, Research Policy 34, 1591-1607; Kim & Bae 2017, Technological Forecasting and Social Change 117, 228-237 | financial valuation; market value; universal patent quality; paper_exact unless manually verified |
| `analyze_competitor_evolution` | `ipc_profile_evolution` / `2.0` | `engineering_screening` | IPC entropy, dominant IPC share and year-to-year cosine distance | publication_date>=90%; applicants>=90%; ipc>=90% | Tang et al. 2012, KDD PatentMiner | PatentMiner DICT; heterogeneous-network co-ranking; paper-exact competitor evolution |

证据等级说明：`descriptive_statistic` 为直接描述统计；`paper_adapted` 只表示部分公式有论文依据且偏差已声明；`engineering_screening` 为工程代理。只有完成原数据/手算复现和适用条件核验后才能使用 `paper_exact`，当前登记表没有任何工具达到该等级。
