import type {
  ProviderAuthMode, ProviderProtocol, ReasoningEffort, ThinkingMode, ToolParameter,
} from "./types";
import type { Locale } from "./i18n";

/**
 * User-facing vocabulary for backend identifiers. Keep the identifiers in
 * values and API payloads, but never expose them as the primary UI label.
 */
export const TOOL_LABELS: Record<string, string> = {
  get_dataset_summary: "数据总览",
  analyze_patent_trend: "公开趋势",
  analyze_lifecycle: "生命周期阶段",
  analyze_ipc_distribution: "IPC 分类分布",
  generate_wordcloud: "技术词云",
  analyze_burst_terms: "近期增长词",
  analyze_yearly_keywords: "逐年关键词",
  analyze_country_distribution: "首次公开局分布",
  analyze_co_network: "申请人合作网络",
  analyze_tech_roadmap: "年度技术主题时间线",
  analyze_tech_matrix: "技术手段—功效矩阵",
  analyze_clustering: "技术主题聚类",
  analyze_patent_valuation: "专利价值筛查",
  analyze_competitor_evolution: "竞争者 IPC 演化",
  search_patents: "相关专利检索",
  read_patent_details: "专利详情深读",
  analyze_entity_portfolio: "主体专利组合",
  analyze_concentration: "竞争集中度",
  analyze_citation_network: "专利引证网络",
  analyze_family_geography: "专利族地域布局",
  audit_search_strategy: "检索策略审计",
  analyze_legal_status: "法律状态分析",
  monitor_patent_changes: "专利变更监测",
  analyze_claim_elements: "权利要求要素分析",
};

const TOOL_LABELS_EN: Record<string, string> = {
  get_dataset_summary: "Dataset overview",
  analyze_patent_trend: "Publication trend",
  analyze_lifecycle: "Lifecycle stage",
  analyze_ipc_distribution: "IPC distribution",
  generate_wordcloud: "Technical word cloud",
  analyze_burst_terms: "Recently growing terms",
  analyze_yearly_keywords: "Yearly keywords",
  analyze_country_distribution: "First publication office distribution",
  analyze_co_network: "Applicant collaboration network",
  analyze_tech_roadmap: "Annual technology timeline",
  analyze_tech_matrix: "Technology-means/effect matrix",
  analyze_clustering: "Technology topic clustering",
  analyze_patent_valuation: "Patent value screening",
  analyze_competitor_evolution: "Competitor IPC evolution",
  search_patents: "Related patent search",
  read_patent_details: "Patent details",
  analyze_entity_portfolio: "Entity patent portfolio",
  analyze_concentration: "Competitive concentration",
  analyze_citation_network: "Patent citation network",
  analyze_family_geography: "Patent family geography",
  audit_search_strategy: "Search strategy audit",
  analyze_legal_status: "Legal status analysis",
  monitor_patent_changes: "Patent change monitoring",
  analyze_claim_elements: "Claim element analysis",
};

const PARAMETER_LABELS: Record<string, string> = {
  query: "检索词",
  top_k: "返回数量",
  top_n: "展示数量",
  n_clusters: "聚类数量",
  year_start: "起始年份",
  year_end: "结束年份",
  ipc_filter: "IPC 筛选",
  applicant_filter: "申请人筛选",
  jurisdiction_filter: "国家/地区筛选",
  patent_numbers: "专利号列表",
  product_features: "产品特征列表",
  retrieval_mode: "检索模式",
  chart_type: "图表粒度",
  text_source: "文本来源",
  vectorization_mode: "文本向量化方式",
  count_mode: "计数口径",
  citation_mode: "引证计算模式",
  entity_type: "主体类型",
  metric: "统计指标",
  group_by_parent: "按母公司归并",
  reviewed_parent_map: "人工复核的母公司映射",
  dimension: "统计维度",
  bootstrap_samples: "稳定性抽样次数",
  strategies: "检索策略列表",
  known_patent_numbers: "已知专利号",
  review_labels: "复核标签",
  random_audit_sample_size: "随机复核样本数",
  strategy_id: "策略编号",
  strategy_version: "策略版本",
  update_baseline: "更新监测基线",
  notification_policy: "提醒策略",
  minimum_event_count: "最少事件数",
  scope: "分析范围",
};

const PARAMETER_HELP: Record<string, string> = {
  query: "输入技术主题、产品名称或限定词；多个条件可直接写在同一检索式中。",
  top_k: "最多返回多少条相关专利，数值越大结果越全面但处理时间可能更长。",
  top_n: "图表或列表中展示的前 N 项。",
  n_clusters: "将专利文本自动分成多少个技术主题，建议从 3–12 开始。",
  year_start: "只分析不早于该年份的记录；留空表示不设起点。",
  year_end: "只分析不晚于该年份的记录；留空表示不设终点。",
  ipc_filter: "按 IPC 分类号筛选，例如 H01M；留空表示全部分类。",
  applicant_filter: "按申请人名称筛选，支持名称片段；留空表示全部申请人。",
  jurisdiction_filter: "按国家/地区或首次公开局筛选，例如 CN、US。",
  patent_numbers: "每行或用逗号分隔一个公开号/专利号。",
  product_features: "每行或用逗号分隔一个待比对的产品特征。",
  retrieval_mode: "词法检索匹配字面关键词；多语言混合检索会融合本地语义模型排序。",
  chart_type: "选择按月份或按年份汇总公开量。",
  text_source: "选择从标题还是摘要中提取技术关键词。",
  vectorization_mode: "选择字符片段或分词后的 TF-IDF 表示方式。",
  count_mode: "同一专利可能有多个 IPC；这里决定按标注次数、去重专利数或专利族归一化。",
  citation_mode: "自动模式按当前数据可用字段选择；其余模式用于筛查或论文复现。",
  entity_type: "选择申请人、受让人、当前权利人或发明人作为统计主体。",
  metric: "选择公开记录、专利族、授权记录或前向引证作为排名指标。",
  group_by_parent: "把已确认属于同一母公司的主体名称合并统计。",
  reviewed_parent_map: "填写已经人工确认的主体归并关系；系统不会自行猜测母公司关系。",
  dimension: "选择按申请人、IPC 分类或首次公开局计算集中度。",
  bootstrap_samples: "用于估计集中度稳定区间的重复抽样次数。",
  strategies: "每个策略包含检索式、筛选条件和版本信息，用于比较查全/查准表现。",
  known_patent_numbers: "已知相关专利号，用来检查检索式是否能找回它们。",
  review_labels: "按人工复核结果标记相关、边界或不相关样本。",
  random_audit_sample_size: "从检索结果中随机抽取多少条进行人工审计。",
  strategy_id: "要监测的检索策略编号。",
  strategy_version: "要监测的检索策略版本；留空使用当前版本。",
  update_baseline: "将本次结果保存为后续变化检测的比较基线。",
  notification_policy: "选择所有变化都提醒，或只有达到事件数阈值时提醒。",
  minimum_event_count: "达到该数量的变化事件后才触发阈值提醒。",
  scope: "可同时限定年份、IPC、申请人、国家/地区和文本字段；留空表示使用当前数据集。",
};

const ENUM_LABELS: Record<string, string> = {
  lexical: "词法检索",
  multilingual_hybrid_beta: "多语言混合检索（测试版）",
  monthly: "按月",
  yearly: "按年",
  title: "标题",
  abstract: "摘要",
  char_ngram_tfidf: "字符 n-gram TF-IDF",
  segmented_word_tfidf: "分词 TF-IDF",
  assignment_count: "按 IPC 标注次数",
  unique_patents: "按去重专利数",
  family_normalized: "按专利族归一化",
  auto: "自动选择",
  screening: "快速筛查",
  replication: "论文复现",
  applicant: "申请人",
  assignee: "受让人",
  owner: "当前权利人",
  inventor: "发明人",
  publications: "公开记录",
  families: "专利族",
  grants: "授权记录",
  citations: "前向引证",
  publication_office: "首次公开局",
  all_changes: "所有变化",
  threshold: "达到阈值时",
  active: "有效/存续",
  pending: "审查中",
  granted: "已授权",
  expired: "已失效",
  abandoned: "已放弃",
  new_publication: "新增公开",
  removed_record: "移除记录",
  updated_record: "记录更新",
  literal_substring: "词面包含匹配",
  en: "英语",
  zh: "中文",
  und: "未知语言",
  high: "高",
  medium: "中",
  low: "低",
  max: "最大",
  default: "默认",
  enabled: "启用",
  disabled: "停用",
  not_tested: "尚未测试",
  passed: "通过",
  connected: "已连接",
  failed: "失败",
  running: "执行中",
  completed: "已完成",
  skipped: "已跳过",
  queued: "排队中",
  parsing: "解析中",
  interrupted: "已中断",
  ready: "就绪",
  archived: "已归档",
  partial: "部分完成",
  cancelled: "已取消",
  awaiting_clarification: "等待补充信息",
  unknown: "未知",
  priority_origin: "优先权来源",
  first_publication_office: "首次公开局",
  family_publication_offices: "专利族公开局",
  designated_states: "指定国家/地区",
  current_active_rights_jurisdictions: "当前有效权利状态的国家/地区",
  manifest: "清单声明",
  user_selected: "用户选择",
  content_signature: "文件内容识别",
};

const FIELD_LABELS: Record<string, string> = {
  answer: "核心结论",
  answer_markdown: "核心结论",
  conclusion: "核心结论",
  summary: "摘要",
  details: "分维度分析",
  findings: "关键发现",
  key_findings: "关键发现",
  key_points: "关键要点",
  trend_summary: "趋势判断",
  methodology: "方法说明",
  limitations: "方法与数据限制",
  warnings: "数据警告",
  recommendations: "建议",
  rank: "排名",
  id: "编号",
  name: "名称",
  label: "名称",
  title: "标题",
  description: "说明",
  total_patents: "专利总量",
  year: "年份",
  year_month: "年月",
  year_start: "起始年份",
  year_end: "结束年份",
  publication_date: "公开日",
  publication_office: "首次公开局",
  country: "国家/地区",
  section: "IPC 分类",
  sections: "IPC 分类",
  ipc: "IPC 分类",
  ipc_sections: "IPC 分类",
  ipc_codes: "IPC 分类号",
  applicant: "申请人",
  applicants: "申请人",
  assignee: "受让人",
  owner: "当前权利人",
  inventor: "发明人",
  canonical_name: "规范化名称",
  original_name: "原始名称",
  record_count: "记录数",
  total_hits: "命中总数",
  total_hits_exact: "命中总数是否精确",
  returned_count: "返回数量",
  query_embedding_time_ms: "语义检索耗时（毫秒）",
  relevance_score: "相关性分数",
  score: "分数",
  score_label: "分数名称",
  score_interval: "分数不确定区间",
  family_size: "专利族规模",
  family_members: "专利族成员",
  backward_citations: "后向引证",
  forward_citations: "前向引证",
  citation_count: "引证次数",
  pagerank: "PageRank 重要性分数",
  dimension: "统计维度",
  metric: "统计指标",
  metric_label: "统计指标",
  count: "数量",
  count_mode: "计数口径",
  hhi: "HHI 集中度指数",
  hhi_bootstrap_95pct: "HHI 95% 稳定区间",
  gini: "Gini 集中度系数",
  shannon_entropy: "Shannon 熵",
  effective_entity_count: "有效主体数",
  effective_entities: "有效主体数",
  metric_value: "指标值",
  family_count: "专利族数量",
  grant_count: "授权数量",
  forward_citation_count: "前向引证数量",
  yearly_publications: "逐年公开量",
  top_ipc_subclasses: "主要 IPC 小类",
  resolution_confidence: "主体解析置信度",
  parent_group: "母公司归并组",
  reviewed_parent_mapping_count: "已复核母公司映射数",
  unresolved_record_count: "未解析记录数",
  low_confidence_mapping_count: "低置信度映射数",
  cr3: "前三主体占比",
  cr5: "前五主体占比",
  cr10: "前十主体占比",
  silhouette_score: "轮廓系数",
  cluster_titles: "聚类标题",
  cluster_keywords: "聚类关键词",
  patents_per_cluster: "各聚类专利数",
  ipc_entropy: "IPC 熵（分类多样性）",
  dominant_ipc_share: "主导 IPC 占比",
  ipc_profile_cosine_shift: "IPC 画像余弦偏移",
  ipc_breadth: "IPC 小类广度",
  patent_age: "专利年龄",
  available_weight_ratio: "可用数据权重",
  confidence_level: "置信水平",
  source_format: "来源格式",
  method: "识别方式",
  matched: "是否匹配",
  error_category: "错误类型",
  formulas: "计算公式",
  analyzed_record_count: "分析记录数",
  current_status_authoritative: "当前法律状态是否权威",
  legal_status_as_of_coverage: "法律状态截至时间字段覆盖率",
  jurisdiction_coverage: "国家/地区字段覆盖率",
  event_type: "事件类型",
  strategy_id: "策略编号",
  strategy_version: "策略版本",
  notification_policy: "提醒策略",
  minimum_event_count: "最少事件数",
  kind_code: "文献种类代码",
  legal_status: "法律状态",
  claims: "权利要求",
  claim_number: "权利要求编号",
  is_independent: "是否独立权利要求",
  language: "文本语言",
  elements: "权利要求要素",
  element_number: "要素编号",
  feature: "产品特征",
  matched_element_numbers: "匹配要素编号",
  match_method: "匹配方法",
  coverage: "覆盖率",
  field_coverage: "字段覆盖率",
  data_as_of: "数据截至时间",
  adapter: "数据适配器",
  version: "版本",
  status: "状态",
  patent_number: "专利号",
  patent_numbers: "专利号列表",
  source_evidence_path: "证据来源路径",
  source_text_sha256: "原文 SHA-256 摘要",
  function: "技术手段",
  effect: "技术功效",
  patent_count: "相关专利数",
  source: "来源节点",
  target: "目标节点",
  weight: "连接权重",
  term: "词语",
  burst: "增长分数",
  early_freq: "历史出现次数",
  late_freq: "近期出现次数",
  text: "文本",
  data: "数据",
  result_type: "结果类型",
  result_metadata: "结果元数据",
  latency_ms: "耗时（毫秒）",
  model_id: "模型标识",
  index_count: "索引数量",
  download_size_mb: "下载大小（MB）",
};

const ADAPTER_LABELS: Record<string, string> = {
  wos_dii: "WoS / Derwent 标记文本（TXT）",
  google_patents_jsonl: "Google Patents JSONL",
  uspto_grant_xml: "USPTO 授权 XML",
  uspto_file_wrapper_json: "USPTO File Wrapper JSON（审查档案）",
  unknown: "未知来源",
};

const PROBE_STAGE_LABELS: Record<string, string> = {
  resolve: "解析服务地址",
  connect: "建立连接",
  authenticate: "验证鉴权",
  models: "获取模型列表",
  chat: "测试对话请求",
  response: "检查响应",
};

const PARAMETER_LABELS_EN: Record<string, string> = {
  query: "Query", top_k: "Results", top_n: "Displayed items", n_clusters: "Clusters",
  year_start: "Start year", year_end: "End year", ipc_filter: "IPC filter",
  applicant_filter: "Applicant filter", jurisdiction_filter: "Jurisdiction filter",
  patent_numbers: "Patent numbers", product_features: "Product features",
  retrieval_mode: "Retrieval mode", chart_type: "Chart granularity", text_source: "Text source",
  vectorization_mode: "Vectorization", count_mode: "Counting mode", citation_mode: "Citation mode",
  entity_type: "Entity type", metric: "Metric", group_by_parent: "Group by parent company",
  reviewed_parent_map: "Reviewed parent mapping", dimension: "Dimension", bootstrap_samples: "Bootstrap samples",
  strategies: "Search strategies", known_patent_numbers: "Known patent numbers", review_labels: "Review labels",
  random_audit_sample_size: "Random audit sample size", strategy_id: "Strategy ID",
  strategy_version: "Strategy version", update_baseline: "Update baseline", notification_policy: "Notification policy",
  minimum_event_count: "Minimum event count", scope: "Analysis scope",
};

const PARAMETER_HELP_EN: Record<string, string> = {
  query: "Enter a technical topic, product name, or qualifier; multiple conditions may be written in one query.",
  top_k: "Maximum related patents to return. Larger values are more comprehensive but may take longer.",
  top_n: "Number of top items shown in a chart or list.",
  n_clusters: "Number of technology topics to infer from patent text; 3–12 is a useful starting range.",
  year_start: "Analyze records from this year onward; leave blank for no lower bound.",
  year_end: "Analyze records through this year; leave blank for no upper bound.",
  ipc_filter: "Filter by an IPC code such as H01M; leave blank for all classifications.",
  applicant_filter: "Filter by an applicant name fragment; leave blank for all applicants.",
  jurisdiction_filter: "Filter by country/region or first publication office, such as CN or US.",
  patent_numbers: "One publication or patent number per line or separated by commas.",
  product_features: "One product feature per line or separated by commas.",
  retrieval_mode: "Lexical search matches literal keywords; multilingual hybrid search combines a local semantic model with lexical ranking.",
  chart_type: "Summarize publications by month or year.",
  text_source: "Extract technical keywords from titles or abstracts.",
  vectorization_mode: "Use character fragments or tokenized TF-IDF representations.",
  count_mode: "A patent may have multiple IPC labels; choose labeled assignments, unique patents, or family-normalized counts.",
  citation_mode: "Automatic mode selects fields available in the current data; other modes support screening or reproducibility.",
  entity_type: "Choose applicant, assignee, current owner, or inventor as the statistical entity.",
  metric: "Rank by publications, patent families, grants, or forward citations.",
  group_by_parent: "Merge entities confirmed to belong to the same parent company.",
  reviewed_parent_map: "Enter manually confirmed entity mappings; the system will not infer parent-company relationships.",
  dimension: "Calculate concentration by applicant, IPC classification, or first publication office.",
  bootstrap_samples: "Repeated samples used to estimate a stable concentration interval.",
  strategies: "Each strategy includes a query, filters, and version information for comparing recall and precision.",
  known_patent_numbers: "Known related patent numbers used to check whether a query retrieves them.",
  review_labels: "Mark samples as relevant, borderline, or irrelevant after manual review.",
  random_audit_sample_size: "Number of search results to sample for manual audit.",
  strategy_id: "Search strategy to monitor.", strategy_version: "Strategy version to monitor; blank uses the current version.",
  update_baseline: "Save this result as the comparison baseline for future change detection.",
  notification_policy: "Notify on all changes or only after an event threshold is reached.",
  minimum_event_count: "Number of change events required before a threshold notification.",
  scope: "Limit by year, IPC, applicant, country/region, and text fields; blank uses the current dataset.",
};

const ENUM_LABELS_EN: Record<string, string> = {
  lexical: "Lexical search", multilingual_hybrid_beta: "Multilingual hybrid (Beta)", monthly: "Monthly", yearly: "Yearly",
  title: "Title", abstract: "Abstract", char_ngram_tfidf: "Character n-gram TF-IDF", segmented_word_tfidf: "Segmented-word TF-IDF",
  assignment_count: "IPC assignments", unique_patents: "Unique patents", family_normalized: "Family-normalized",
  auto: "Automatic", screening: "Screening", replication: "Reproducibility", applicant: "Applicant", assignee: "Assignee",
  owner: "Current owner", inventor: "Inventor", publications: "Publications", families: "Patent families", grants: "Grants",
  citations: "Forward citations", publication_office: "First publication office", all_changes: "All changes", threshold: "At threshold",
  active: "Active", pending: "Pending", granted: "Granted", expired: "Expired", abandoned: "Abandoned",
  new_publication: "New publication", removed_record: "Removed record", updated_record: "Updated record", literal_substring: "Literal substring",
  en: "English", zh: "Chinese", und: "Unknown language", high: "High", medium: "Medium", low: "Low", max: "Maximum", default: "Default",
  enabled: "Enabled", disabled: "Disabled", not_tested: "Not tested", passed: "Passed", connected: "Connected", failed: "Failed",
  running: "Running", completed: "Completed", skipped: "Skipped", queued: "Queued", parsing: "Parsing", interrupted: "Interrupted",
  ready: "Ready", archived: "Archived", partial: "Partial", cancelled: "Cancelled", awaiting_clarification: "Awaiting clarification",
  unknown: "Unknown", priority_origin: "Priority origin", first_publication_office: "First publication office",
  family_publication_offices: "Family publication offices", designated_states: "Designated states",
  current_active_rights_jurisdictions: "Jurisdictions with current active rights", manifest: "Manifest declaration",
  user_selected: "User selected", content_signature: "File content signature",
};

const FIELD_LABELS_EN: Record<string, string> = {
  answer: "Key conclusion", answer_markdown: "Key conclusion", conclusion: "Key conclusion", summary: "Summary", details: "Analysis by dimension",
  findings: "Key findings", key_findings: "Key findings", key_points: "Key points", trend_summary: "Trend assessment", methodology: "Methodology",
  limitations: "Method and data limitations", warnings: "Data warnings", recommendations: "Recommendations", rank: "Rank", id: "ID", name: "Name",
  label: "Name", title: "Title", description: "Description", total_patents: "Total patents", year: "Year", year_month: "Year-month",
  year_start: "Start year", year_end: "End year", publication_date: "Publication date", publication_office: "First publication office",
  country: "Country/region", section: "IPC classification", sections: "IPC classification", ipc: "IPC classification", ipc_sections: "IPC sections",
  ipc_codes: "IPC codes", applicant: "Applicant", applicants: "Applicants", assignee: "Assignee", owner: "Current owner", inventor: "Inventor",
  canonical_name: "Canonical name", original_name: "Original name", record_count: "Record count", total_hits: "Total hits",
  total_hits_exact: "Total hits exact", returned_count: "Returned count", query_embedding_time_ms: "Semantic search time (ms)",
  relevance_score: "Relevance score", score: "Score", score_label: "Score label", score_interval: "Score interval", family_size: "Family size",
  family_members: "Family members", backward_citations: "Backward citations", forward_citations: "Forward citations", citation_count: "Citation count",
  pagerank: "PageRank importance", dimension: "Dimension", metric: "Metric", metric_label: "Metric", count: "Count", count_mode: "Counting mode",
  hhi: "HHI concentration", hhi_bootstrap_95pct: "HHI 95% stable interval", gini: "Gini concentration", shannon_entropy: "Shannon entropy",
  effective_entity_count: "Effective entity count", effective_entities: "Effective entities", metric_value: "Metric value", family_count: "Family count",
  grant_count: "Grant count", forward_citation_count: "Forward citation count", yearly_publications: "Yearly publications", top_ipc_subclasses: "Top IPC subclasses",
  resolution_confidence: "Entity resolution confidence", parent_group: "Parent-company group", reviewed_parent_mapping_count: "Reviewed parent mappings",
  unresolved_record_count: "Unresolved records", low_confidence_mapping_count: "Low-confidence mappings", cr3: "Top-three share", cr5: "Top-five share", cr10: "Top-ten share",
  silhouette_score: "Silhouette score", cluster_titles: "Cluster titles", cluster_keywords: "Cluster keywords", patents_per_cluster: "Patents per cluster",
  ipc_entropy: "IPC entropy (classification diversity)", dominant_ipc_share: "Dominant IPC share", ipc_profile_cosine_shift: "IPC cosine shift",
  ipc_breadth: "IPC breadth", patent_age: "Patent age", available_weight_ratio: "Available data weight", confidence_level: "Confidence level",
  source_format: "Source format", method: "Recognition method", matched: "Matched", error_category: "Error category", formulas: "Formulas",
  analyzed_record_count: "Analyzed records", current_status_authoritative: "Current legal status authoritative", legal_status_as_of_coverage: "Legal-status-as-of coverage",
  jurisdiction_coverage: "Jurisdiction coverage", event_type: "Event type", strategy_id: "Strategy ID", strategy_version: "Strategy version",
  notification_policy: "Notification policy", minimum_event_count: "Minimum event count", kind_code: "Document kind code", legal_status: "Legal status",
  claims: "Claims", claim_number: "Claim number", is_independent: "Independent claim", language: "Text language", elements: "Claim elements",
  element_number: "Element number", feature: "Product feature", matched_element_numbers: "Matched element numbers", match_method: "Matching method",
  coverage: "Coverage", field_coverage: "Field coverage", data_as_of: "Data as of", adapter: "Data adapter", version: "Version", status: "Status",
  patent_number: "Patent number", patent_numbers: "Patent numbers", source_evidence_path: "Evidence source path", source_text_sha256: "Source text SHA-256",
  function: "Technology means", effect: "Technical effect", patent_count: "Related patents", source: "Source node", target: "Target node", weight: "Connection weight",
  term: "Term", burst: "Burst score", early_freq: "Historical frequency", late_freq: "Recent frequency", text: "Text", data: "Data", result_type: "Result type",
  result_metadata: "Result metadata", latency_ms: "Latency (ms)", model_id: "Model ID", index_count: "Index count", download_size_mb: "Download size (MB)",
};

const ADAPTER_LABELS_EN: Record<string, string> = {
  wos_dii: "WoS / Derwent tagged text (TXT)", google_patents_jsonl: "Google Patents JSONL", uspto_grant_xml: "USPTO grant XML",
  uspto_file_wrapper_json: "USPTO File Wrapper JSON (prosecution file)", unknown: "Unknown source",
};

const PROBE_STAGE_LABELS_EN: Record<string, string> = {
  resolve: "Resolve service address", connect: "Establish connection", authenticate: "Authenticate", models: "Get model list",
  chat: "Test chat request", response: "Check response",
};

const choose = (locale: Locale, zh: string, en?: string): string => locale === "en-US" ? (en || zh) : zh;

export function toolLabel(name?: string, locale: Locale = "zh-CN"): string {
  if (!name) return choose(locale, "分析工具", "Analysis tool");
  const labels = locale === "en-US" ? TOOL_LABELS_EN : TOOL_LABELS;
  return labels[name] || choose(locale, `分析工具（${name}）`, `Analysis tool (${name})`);
}

export function toolOrTextLabel(value: unknown, locale: Locale = "zh-CN"): string {
  if (typeof value !== "string") return choose(locale, "分析步骤", "Analysis step");
  const labels = locale === "en-US" ? TOOL_LABELS_EN : TOOL_LABELS;
  return labels[value] ? toolLabel(value, locale) : value;
}

export function parameterLabel(name: string, locale: Locale = "zh-CN"): string {
  const labels = locale === "en-US" ? PARAMETER_LABELS_EN : PARAMETER_LABELS;
  return labels[name] || choose(locale, `其他参数（${name}）`, `Other parameter (${name})`);
}

export function parameterHelp(name: string, schema?: ToolParameter, locale: Locale = "zh-CN"): string {
  const helpMap = locale === "en-US" ? PARAMETER_HELP_EN : PARAMETER_HELP;
  const help = helpMap[name] || schema?.description || choose(locale, "用于限定本次分析范围或计算方式。", "Limits the scope or calculation for this analysis.");
  const range = schema && (schema.minimum != null || schema.maximum != null)
    ? choose(locale, `取值范围：${schema.minimum ?? "不限"}–${schema.maximum ?? "不限"}。`, `Range: ${schema.minimum ?? "unlimited"}–${schema.maximum ?? "unlimited"}.`) : "";
  const defaultValue = schema?.default !== undefined ? choose(locale, `默认：${formatDisplayValue(schema.default, undefined, locale)}。`, `Default: ${formatDisplayValue(schema.default, undefined, locale)}.`) : "";
  return `${help}${range}${defaultValue}`;
}

export function enumLabel(value: string, locale: Locale = "zh-CN"): string {
  const labels = locale === "en-US" ? ENUM_LABELS_EN : ENUM_LABELS;
  if (labels[value]) return labels[value];
  return /[\u3400-\u9fff]/.test(value) ? value : choose(locale, `其他选项（${value}）`, `Other option (${value})`);
}

const METRIC_LABEL_KEYS: Record<string, string> = {
  "IPC 标注次数": "assignment_count",
  "含该 IPC 部级的去重专利数": "unique_patents",
  "含该 IPC 部级的去重同族数": "family_normalized",
};

/** Localize the known IPC metric labels emitted by the backend. */
export function metricLabel(value?: unknown, locale: Locale = "zh-CN"): string {
  if (typeof value !== "string" || !value) return choose(locale, "统计指标", "Metric");
  const key = METRIC_LABEL_KEYS[value] || value;
  const known = key === "assignment_count" || key === "unique_patents" || key === "family_normalized";
  return known ? enumLabel(key, locale) : value;
}

export function fieldLabel(key: string, locale: Locale = "zh-CN"): string {
  const labels = locale === "en-US" ? FIELD_LABELS_EN : FIELD_LABELS;
  return labels[key] || choose(locale, `数据字段（${key}）`, `Data field (${key})`);
}

export function statusLabel(value?: unknown, locale: Locale = "zh-CN"): string {
  if (typeof value !== "string") return choose(locale, "未知状态", "Unknown status");
  const labels = locale === "en-US" ? ENUM_LABELS_EN : ENUM_LABELS;
  return labels[value] || choose(locale, `状态（${value}）`, `Status (${value})`);
}

export function importStatusLabel(value?: unknown, locale: Locale = "zh-CN"): string {
  return statusLabel(value, locale);
}

export function adapterLabel(value?: unknown, locale: Locale = "zh-CN"): string {
  const labels = locale === "en-US" ? ADAPTER_LABELS_EN : ADAPTER_LABELS;
  if (typeof value !== "string" || !value) return labels.unknown;
  return labels[value] || choose(locale, `数据适配器（${value}）`, `Data adapter (${value})`);
}

export function jurisdictionLabel(value?: unknown, locale: Locale = "zh-CN"): string {
  if (typeof value !== "string") return choose(locale, "未知国家/地区", "Unknown country/region");
  const labels: Record<string, string> = {
    CN: "中国（CN）", US: "美国（US）", EP: "欧洲专利局（EP）", WO: "世界知识产权组织（WO）",
    JP: "日本（JP）", KR: "韩国（KR）", DE: "德国（DE）", GB: "英国（GB）",
  };
  const labelsEn: Record<string, string> = {
    CN: "China (CN)", US: "United States (US)", EP: "European Patent Office (EP)", WO: "World Intellectual Property Organization (WO)",
    JP: "Japan (JP)", KR: "South Korea (KR)", DE: "Germany (DE)", GB: "United Kingdom (GB)",
  };
  return (locale === "en-US" ? labelsEn : labels)[value] || value;
}

export function languageLabel(value?: unknown, locale: Locale = "zh-CN"): string {
  return typeof value === "string" ? enumLabel(value, locale) : choose(locale, "未知语言", "Unknown language");
}

export function recommendationCategoryLabel(value?: unknown, locale: Locale = "zh-CN"): string {
  if (typeof value !== "string") return choose(locale, "建议", "Recommendation");
  const labels: Record<string, string> = {
    recall: "查全率",
    precision: "查准率",
    coverage: "覆盖范围",
    validation: "结果验证",
    legal: "法律风险",
  };
  const labelsEn: Record<string, string> = {
    recall: "Recall", precision: "Precision", coverage: "Coverage", validation: "Validation", legal: "Legal risk",
  };
  return (locale === "en-US" ? labelsEn : labels)[value] || value;
}

export function intentLabel(value?: unknown, locale: Locale = "zh-CN"): string {
  if (typeof value !== "string" || !value) return "";
  const labels: Record<string, string> = {
    trend: "趋势分析",
    landscape: "技术格局",
    search: "专利检索",
    detail: "专利详情",
    valuation: "价值评估",
    monitoring: "变化监测",
    compliance: "合规分析",
  };
  const labelsEn: Record<string, string> = {
    trend: "Trend analysis", landscape: "Technology landscape", search: "Patent search", detail: "Patent details",
    valuation: "Value assessment", monitoring: "Change monitoring", compliance: "Compliance analysis",
  };
  return (locale === "en-US" ? labelsEn : labels)[value] || value;
}

export function originLabel(value?: unknown, locale: Locale = "zh-CN"): string {
  if (value === "reused") return choose(locale, "复用已有证据", "Reused evidence");
  if (value === "new") return choose(locale, "本轮新执行", "New execution");
  return typeof value === "string" && value ? choose(locale, `来源（${value}）`, `Source (${value})`) : "";
}

export function protocolLabel(protocol?: ProviderProtocol | string, locale: Locale = "zh-CN"): string {
  const labels: Record<string, string> = {
    openai_chat: "OpenAI 对话接口",
    anthropic_messages: "Anthropic 消息接口",
    deepseek_chat: "DeepSeek 对话接口",
  };
  const labelsEn: Record<string, string> = {
    openai_chat: "OpenAI chat API", anthropic_messages: "Anthropic messages API", deepseek_chat: "DeepSeek chat API",
  };
  return (locale === "en-US" ? labelsEn : labels)[protocol || ""] || choose(locale, `接口协议（${protocol || "未指定"}）`, `Protocol (${protocol || "not specified"})`);
}

export function authModeLabel(mode?: ProviderAuthMode | string, locale: Locale = "zh-CN"): string {
  const labels: Record<string, string> = {
    bearer: "Bearer 令牌（Token）",
    x_api_key: "x-api-key 请求头",
    custom_header: "自定义请求头（Header）",
    none: "无鉴权",
  };
  const labelsEn: Record<string, string> = {
    bearer: "Bearer token", x_api_key: "x-api-key header", custom_header: "Custom header", none: "No authentication",
  };
  return (locale === "en-US" ? labelsEn : labels)[mode || ""] || choose(locale, `鉴权方式（${mode || "未指定"}）`, `Authentication (${mode || "not specified"})`);
}

export function reasoningEffortLabel(value?: ReasoningEffort | string, locale: Locale = "zh-CN"): string {
  return value === "default" ? choose(locale, "默认", "Default") : enumLabel(value || "default", locale);
}

export function thinkingModeLabel(value?: ThinkingMode | string, locale: Locale = "zh-CN"): string {
  return enumLabel(value || "auto", locale);
}

export function probeStageLabel(value?: string, locale: Locale = "zh-CN"): string {
  const labels = locale === "en-US" ? PROBE_STAGE_LABELS_EN : PROBE_STAGE_LABELS;
  return labels[value || ""] || (value ? choose(locale, `阶段（${value}）`, `Stage (${value})`) : choose(locale, "测试阶段", "Test stage"));
}

export function errorCategoryLabel(value?: unknown, locale: Locale = "zh-CN"): string {
  if (typeof value !== "string" || !value) return "";
  const labels: Record<string, string> = {
    authentication: "鉴权失败",
    model: "模型不可用",
    address: "地址或网络错误",
    capability: "能力不兼容",
    protocol: "协议或参数错误",
    provider: "供应商错误",
    import_failed: "导入失败",
    data_insufficient: "数据不足",
    input_validation: "输入校验失败",
    algorithm_failure: "算法执行失败",
    provider_failure: "供应商调用失败",
    synthesis_failure: "总结生成失败",
    system_failure: "系统错误",
  };
  const labelsEn: Record<string, string> = {
    authentication: "Authentication failure", model: "Model unavailable", address: "Address or network error", capability: "Incompatible capability",
    protocol: "Protocol or parameter error", provider: "Provider error", import_failed: "Import failed", data_insufficient: "Insufficient data",
    input_validation: "Input validation failed", algorithm_failure: "Algorithm failed", provider_failure: "Provider call failed",
    synthesis_failure: "Summary generation failed", system_failure: "System error",
  };
  return (locale === "en-US" ? labelsEn : labels)[value] || choose(locale, `错误类型（${value}）`, `Error category (${value})`);
}

export function httpStatusLabel(status: number, statusText?: string, locale: Locale = "zh-CN"): string {
  const labels: Record<number, string> = {
    400: "请求无效",
    401: "未授权，请检查接口密钥",
    403: "没有权限访问该资源",
    404: "请求的资源不存在",
    409: "请求发生冲突",
    422: "请求参数校验失败",
    429: "请求过于频繁，请稍后再试",
    500: "服务器内部错误",
    502: "上游服务响应异常",
    503: "服务暂时不可用",
    504: "服务响应超时",
  };
  const labelsEn: Record<number, string> = {
    400: "Invalid request", 401: "Unauthorized; check the API key", 403: "You do not have access to this resource", 404: "Resource not found",
    409: "Request conflict", 422: "Request validation failed", 429: "Too many requests; try again later", 500: "Internal server error",
    502: "Upstream service error", 503: "Service temporarily unavailable", 504: "Service response timed out",
  };
  return (locale === "en-US" ? labelsEn : labels)[status] || choose(locale,
    `请求失败（HTTP ${status}${statusText && !/^[A-Za-z ]+$/.test(statusText) ? `：${statusText}` : ""}）`,
    `Request failed (HTTP ${status}${statusText && !/^[A-Za-z ]+$/.test(statusText) ? `: ${statusText}` : ""})`);
}

export function localizeErrorMessage(message: string, locale: Locale = "zh-CN"): string {
  const labels: Record<string, string> = {
    "client.network": "无法连接后端服务，请检查后端是否已启动。",
    "client.sse.invalidEvent": "服务器返回了无法解析的 SSE 事件",
    "client.sse.incomplete": "对话流在最终完成事件之前中断",
    "Internal Server Error": "服务器内部错误",
    "Bad Request": "请求无效",
    Unauthorized: "未授权，请检查接口密钥",
    Forbidden: "没有权限访问该资源",
    "Not Found": "请求的资源不存在",
    "Failed to fetch": "无法连接后端服务，请检查后端是否已启动。",
    "NetworkError when attempting to fetch resource.": "无法连接后端服务，请检查后端是否已启动。",
  };
  const labelsEn: Record<string, string> = {
    "client.network": "Cannot connect to the backend; check that it is running.",
    "client.sse.invalidEvent": "The server returned an unparseable SSE event",
    "client.sse.incomplete": "The conversation stream stopped before the final completion event",
    "Internal Server Error": "Internal server error",
    "Bad Request": "Invalid request",
    Unauthorized: "Unauthorized; check the API key",
    Forbidden: "You do not have access to this resource",
    "Not Found": "Resource not found",
    "Failed to fetch": "Cannot connect to the backend; check that it is running.",
    "NetworkError when attempting to fetch resource.": "Cannot connect to the backend; check that it is running.",
    "服务器内部错误": "Internal server error",
    "请求无效": "Invalid request",
    "未授权，请检查接口密钥": "Unauthorized; check the API key",
    "没有权限访问该资源": "You do not have access to this resource",
    "请求的资源不存在": "Resource not found",
    "请求发生冲突": "Request conflict",
    "请求参数校验失败": "Request validation failed",
    "请求过于频繁，请稍后再试": "Too many requests; try again later",
    "上游服务响应异常": "Upstream service error",
    "服务暂时不可用": "Service temporarily unavailable",
    "服务响应超时": "Service response timed out",
    "无法连接后端服务，请检查后端是否已启动。": "Cannot connect to the backend; check that it is running.",
    "服务器返回了无法解析的 SSE 事件": "The server returned an unparseable SSE event",
    "对话流在最终完成事件之前中断": "The conversation stream stopped before the final completion event",
  };
  const stableHttpStatus = message.match(/^client\.http\.(\d+)(?::([\s\S]*))?$/);
  if (stableHttpStatus) {
    return httpStatusLabel(Number(stableHttpStatus[1]), stableHttpStatus[2], locale);
  }
  if (locale === "en-US") {
    // httpStatusLabel() is intentionally locale-neutral at the API boundary
    // and historically produced this Chinese client-side wrapper. Normalize
    // only that exact shape; arbitrary backend details must remain unchanged.
    const unknownHttpStatus = message.match(/^请求失败（HTTP (\d+)(?:：(.+))?）$/);
    if (unknownHttpStatus) {
      return `Request failed (HTTP ${unknownHttpStatus[1]}${unknownHttpStatus[2] ? `: ${unknownHttpStatus[2]}` : ""})`;
    }
  }
  return (locale === "en-US" ? labelsEn : labels)[message] || message;
}

export function formatDisplayValue(
  value: unknown, key?: string, locale: Locale = "zh-CN", translateValues = true,
): string {
  if (value == null || value === "") return "—";
  if (!translateValues) {
    if (Array.isArray(value)) {
      return value.map(item => formatDisplayValue(item, undefined, locale, false)).join(", ") || "—";
    }
    if (typeof value === "object") return formatDisplayJson(value, locale, false);
    return String(value);
  }
  if (typeof value === "boolean") return value ? choose(locale, "是", "Yes") : choose(locale, "否", "No");
  if (Array.isArray(value)) return value.map(item => formatDisplayValue(item, key, locale)).join(locale === "en-US" ? ", " : "、") || "—";
  if (typeof value === "object") return formatDisplayJson(value, locale);
  if (key === "country" || key === "publication_office" || key === "jurisdiction") return jurisdictionLabel(value, locale);
  if (key === "language") return languageLabel(value, locale);
  if (key === "adapter" || key === "source_format") return adapterLabel(value, locale);
  if (key === "error_category") return errorCategoryLabel(value, locale);
  if (key === "metric_label") return metricLabel(value, locale);
  if (["status", "legal_status", "event_type", "match_method", "count_mode", "metric", "dimension", "notification_policy", "method", "probe_status"].includes(key || "")) return enumLabel(String(value), locale);
  return String(value);
}

function displayJsonValue(value: unknown, key?: string, locale: Locale = "zh-CN", translateValues = true): unknown {
  if (Array.isArray(value)) return value.map(item => displayJsonValue(item, key, locale, translateValues));
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value as Record<string, unknown>).map(([childKey, childValue]) => [fieldLabel(childKey, locale), displayJsonValue(childValue, childKey, locale, translateValues)]));
  }
  return value == null || value === "" ? "—" : formatDisplayValue(value, key, locale, translateValues);
}

export function formatDisplayJson(value: unknown, locale: Locale = "zh-CN", translateValues = true): string {
  return JSON.stringify(displayJsonValue(value, undefined, locale, translateValues), null, 2);
}
