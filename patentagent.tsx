import React, { useState, useEffect, useRef } from 'react';
import { 
  Database, Settings, Download, Send, Bot, User, 
  BarChart2, PieChart, Activity, Map, Network, 
  TrendingUp, Layers, Zap, FolderSearch, CheckCircle2, 
  XCircle, Loader2, Lightbulb, ChevronDown, ChevronRight
} from 'lucide-react';

// ==========================================
// 1. Types & Interfaces (按方案定义)
// ==========================================
interface DataSummary {
  total_patents: number;
  year_range: [number, number];
  ipc_sections: string[];
  top_applicants: { name: string; count: number }[];
}

interface ToolStep {
  id: string;
  tool: string;
  status: 'running' | 'completed' | 'failed';
  duration_ms?: number;
  chart_html?: string | null;
  error?: string | null;
}

interface Rec {
  category: string;
  recommendation: string;
  urgency: number;
}

interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  intent?: string;
  steps?: ToolStep[];
  recommendations?: Rec[];
}

// ==========================================
// 2. Mock Backend & SSE Simulation
// ==========================================
// 模拟图表生成的 HTML
const generateMockChart = (title: string) => `
  <!DOCTYPE html>
  <html>
  <head>
    <style>
      body { font-family: ui-sans-serif, system-ui, -apple-system, sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0; background: #f8fafc; color: #334155; }
      h4 { margin: 0 0 16px 0; color: #0f172a; font-weight: 600; }
      .chart-container { display: flex; align-items: flex-end; gap: 12px; height: 180px; padding: 20px; background: white; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
      .bar-wrapper { display: flex; flex-direction: column; align-items: center; gap: 8px; }
      .bar { width: 36px; background: linear-gradient(to top, #3b82f6, #60a5fa); border-radius: 4px 4px 0 0; transition: height 0.5s ease; animation: grow 0.8s ease-out forwards; }
      .label { font-size: 12px; font-weight: 500; color: #64748b; }
      @keyframes grow { from { height: 0; opacity: 0; } to { opacity: 1; } }
    </style>
  </head>
  <body>
    <h4>${title} - 模拟可视化</h4>
    <div class="chart-container">
      ${[45, 80, 60, 110, 95].map((h, i) => `
        <div class="bar-wrapper">
          <div class="bar" style="height: ${h}px;"></div>
          <div class="label">201${8 + i}</div>
        </div>
      `).join('')}
    </div>
  </body>
  </html>
`;

// ==========================================
// 3. Components
// ==========================================

// --- Chart Frame (iframe 渲染器) ---
const ChartFrame = ({ html, height = 300 }: { html: string; height?: number }) => (
  <iframe
    srcDoc={html}
    style={{ width: '100%', height, border: 'none', borderRadius: '0.5rem' }}
    sandbox="allow-scripts"
    className="bg-slate-50 border border-slate-200"
  />
);

// --- Tool Step (工具执行卡片) ---
const ToolStepCard = ({ step }: { step: ToolStep }) => {
  const [expanded, setExpanded] = useState(step.status === 'completed');

  return (
    <div className="my-3 border border-slate-200 rounded-lg bg-white overflow-hidden shadow-sm">
      <div 
        className="flex items-center justify-between p-3 cursor-pointer hover:bg-slate-50 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2 text-sm font-medium text-slate-700">
          {step.status === 'running' && <Loader2 className="w-4 h-4 animate-spin text-blue-500" />}
          {step.status === 'completed' && <CheckCircle2 className="w-4 h-4 text-emerald-500" />}
          {step.status === 'failed' && <XCircle className="w-4 h-4 text-rose-500" />}
          <span className="font-mono text-xs bg-slate-100 px-2 py-1 rounded text-slate-600">
            🔧 {step.tool}
          </span>
          {step.status === 'completed' && (
            <span className="text-slate-400 text-xs ml-2">完成 · {step.duration_ms}ms</span>
          )}
        </div>
        {expanded ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
      </div>
      
      {expanded && step.chart_html && (
        <div className="p-3 border-t border-slate-100 bg-slate-50">
          <ChartFrame html={step.chart_html} />
        </div>
      )}
      {expanded && step.error && (
        <div className="p-3 text-sm text-rose-600 bg-rose-50 border-t border-rose-100">
          {step.error}
        </div>
      )}
    </div>
  );
};

// --- Message Bubble (单条消息) ---
const MessageBubble = ({ message }: { message: Message }) => {
  const isUser = message.role === 'user';

  return (
    <div className={`flex gap-4 p-4 ${isUser ? 'bg-transparent' : 'bg-white rounded-xl shadow-sm border border-slate-100'}`}>
      <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${isUser ? 'bg-indigo-100 text-indigo-600' : 'bg-blue-600 text-white'}`}>
        {isUser ? <User className="w-5 h-5" /> : <Bot className="w-5 h-5" />}
      </div>
      <div className="flex-1 overflow-hidden">
        <div className="font-semibold text-sm text-slate-800 mb-1 flex items-center gap-2">
          {isUser ? '用户' : 'Agent'}
          {message.intent && (
            <span className="text-[10px] bg-blue-50 text-blue-600 px-2 py-0.5 rounded-full border border-blue-100 font-normal">
              意图: {message.intent}
            </span>
          )}
        </div>
        
        {/* 工具执行步骤区 */}
        {message.steps && message.steps.length > 0 && (
          <div className="mb-3">
            {message.steps.map(step => (
              <ToolStepCard key={step.id} step={step} />
            ))}
          </div>
        )}
        
        {/* 文本内容区 */}
        {message.content && (
          <div className="text-slate-700 text-sm leading-relaxed whitespace-pre-wrap">
            {message.content}
          </div>
        )}

        {/* 策略建议区 */}
        {message.recommendations && message.recommendations.length > 0 && (
          <div className="mt-4 grid gap-2">
            <div className="text-xs font-semibold text-slate-500 mb-1 flex items-center gap-1">
              <Lightbulb className="w-4 h-4" /> 分析建议
            </div>
            {message.recommendations.map((rec, i) => (
              <div key={i} className="bg-amber-50 border border-amber-100 p-3 rounded-lg flex items-start gap-3">
                <span className="bg-amber-200 text-amber-800 text-[10px] px-2 py-1 rounded font-medium mt-0.5 whitespace-nowrap">
                  {rec.category}
                </span>
                <p className="text-sm text-amber-900 m-0">{rec.recommendation}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

// ==========================================
// 4. Main Application (路由+全局状态)
// ==========================================
export default function App() {
  const [dataSummary, setDataSummary] = useState<DataSummary | null>(null);
  const [dirInput, setDirInput] = useState('/data/patents/lithium_battery_2023');
  const [isDataLoading, setIsDataLoading] = useState(false);
  
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'init-1',
      role: 'assistant',
      content: '您好，我是 PatentAgent 专利分析助手。您可以加载左侧的数据集，然后在下方告诉我您的分析需求，或者直接点击右侧的快捷工具进行分析。'
    }
  ]);
  const [inputText, setInputText] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 快捷工具列表
  const quickTools = [
    { name: '数据总览', icon: Database, action: 'analyze_summary' },
    { name: '趋势分析', icon: TrendingUp, action: 'analyze_trend' },
    { name: '增长趋势', icon: Activity, action: 'analyze_growth' },
    { name: 'IPC热力图', icon: Layers, action: 'analyze_ipc' },
    { name: '词云热点', icon: PieChart, action: 'analyze_keywords' },
    { name: '国家分布', icon: Map, action: 'analyze_geo' },
    { name: '合作网络', icon: Network, action: 'analyze_network' },
    { name: '价值评估', icon: Zap, action: 'evaluate_value' },
  ];

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // 模拟加载数据
  const handleLoadData = () => {
    setIsDataLoading(true);
    setTimeout(() => {
      setDataSummary({
        total_patents: 68432,
        year_range: [2018, 2022],
        ipc_sections: ['H01M', 'B60L', 'Y02E', 'C01G'],
        top_applicants: [
          { name: '宁德时代新能源科技股份有限公司', count: 4210 },
          { name: 'LG化学株式会社', count: 3890 },
          { name: '丰田自动车株式会社', count: 3105 }
        ]
      });
      setIsDataLoading(false);
    }, 1200);
  };

  // 核心：模拟 Agent SSE 对话流
  const handleSendMessage = async (customText?: string, forcedTool?: string) => {
    const textToSend = customText || inputText;
    if (!textToSend.trim() && !forcedTool) return;
    
    // 1. 添加用户消息
    const userMsgId = Date.now().toString();
    setMessages(prev => [...prev, { id: userMsgId, role: 'user', content: textToSend }]);
    setInputText('');
    setIsStreaming(true);

    // 2. 初始化 Agent 消息 (准备接收流)
    const agentMsgId = (Date.now() + 1).toString();
    setMessages(prev => [...prev, { 
      id: agentMsgId, 
      role: 'assistant', 
      content: '', 
      intent: '分析中...', 
      steps: [] 
    }]);

    const updateAgentMsg = (updater: (msg: Message) => Message) => {
      setMessages(prev => prev.map(msg => msg.id === agentMsgId ? updater(msg) : msg));
    };

    // --- 模拟 SSE 事件流序列 ---
    const delay = (ms: number) => new Promise(res => setTimeout(res, ms));

    await delay(600);
    // Event: intent
    updateAgentMsg(msg => ({ ...msg, intent: forcedTool ? '执行指定工具' : '技术趋势分析' }));

    await delay(400);
    // Event: step (running)
    const stepId = 'step-' + Date.now();
    const toolName = forcedTool || 'analyze_patent_trend';
    updateAgentMsg(msg => ({
      ...msg,
      steps: [{ id: stepId, tool: toolName, status: 'running' }]
    }));

    await delay(1800);
    // Event: step (completed with chart)
    updateAgentMsg(msg => ({
      ...msg,
      steps: msg.steps?.map(s => s.id === stepId ? { 
        ...s, 
        status: 'completed', 
        duration_ms: 1842, 
        chart_html: generateMockChart(textToSend || toolName) 
      } : s)
    }));

    await delay(500);
    // Event: text (Typewriter effect)
    const finalText = `根据${dataSummary ? '当前加载的' : ''}数据分析，该领域近五年申请量稳步增长，特别是在2020年之后迎来了爆发期。\n\n主要驱动力来自于新能源汽车市场的扩大以及储能技术的突破。建议重点关注头部企业的专利布局空白区域。`;
    
    for (let i = 0; i <= finalText.length; i++) {
      updateAgentMsg(msg => ({ ...msg, content: finalText.substring(0, i) }));
      await delay(30); // 打字速度
    }

    await delay(600);
    // Event: strategy
    updateAgentMsg(msg => ({
      ...msg,
      recommendations: [
        { category: '创新空白', recommendation: '固态电池固态电解质界面阻抗问题相关专利较少，属于技术蓝海。', urgency: 5 },
        { category: '预警', recommendation: 'H01M 10/0525 (锂离子电池) 领域头部企业壁垒极高，建议采取外围包抄策略。', urgency: 4 }
      ]
    }));

    // Event: done
    setIsStreaming(false);
  };

  return (
    <div className="h-screen w-screen flex flex-col bg-slate-50 text-slate-900 font-sans overflow-hidden">
      {/* --- Top Navbar --- */}
      <header className="h-14 bg-white border-b border-slate-200 flex items-center justify-between px-6 shrink-0 z-10 relative">
        <div className="flex items-center gap-2 text-blue-700 font-bold text-lg tracking-tight">
          <div className="bg-blue-600 text-white p-1.5 rounded-lg shadow-sm shadow-blue-200">
            <Bot className="w-5 h-5" />
          </div>
          PatentAgent <span className="text-slate-400 font-normal text-sm ml-2 border-l border-slate-300 pl-2">企业级专利分析专家</span>
        </div>
        <div className="flex gap-3">
          <button className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100 rounded-md transition-colors border border-slate-200 shadow-sm">
            <Download className="w-4 h-4" /> 导出报告
          </button>
          <button className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100 rounded-md transition-colors">
            <Settings className="w-4 h-4" /> 设置
          </button>
        </div>
      </header>

      {/* --- Main Layout --- */}
      <main className="flex-1 flex overflow-hidden">
        
        {/* --- Left Sidebar: Data & Settings --- */}
        <aside className="w-[300px] bg-white border-r border-slate-200 flex flex-col overflow-y-auto shrink-0 shadow-[4px_0_24px_rgba(0,0,0,0.02)] z-10">
          
          {/* Data Management Panel */}
          <div className="p-5 border-b border-slate-100">
            <h2 className="text-sm font-bold text-slate-800 uppercase tracking-wider mb-4 flex items-center gap-2">
              <Database className="w-4 h-4 text-blue-500" /> 数据管理
            </h2>
            <div className="mb-3">
              <label className="block text-xs font-medium text-slate-500 mb-1.5">本地数据目录 / 知识库名称</label>
              <div className="relative">
                <FolderSearch className="w-4 h-4 absolute left-2.5 top-2.5 text-slate-400" />
                <input 
                  type="text" 
                  value={dirInput}
                  onChange={(e) => setDirInput(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
                />
              </div>
            </div>
            <button 
              onClick={handleLoadData}
              disabled={isDataLoading}
              className="w-full py-2 bg-slate-800 hover:bg-slate-900 text-white text-sm font-medium rounded-lg shadow-sm transition-colors flex items-center justify-center gap-2 disabled:opacity-70"
            >
              {isDataLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : '加载并索引数据'}
            </button>

            {/* Data Summary Display */}
            {dataSummary && (
              <div className="mt-5 p-4 bg-slate-50 border border-slate-100 rounded-xl">
                <div className="text-xs font-semibold text-slate-500 mb-3 uppercase tracking-wider">数据概况</div>
                <div className="grid grid-cols-2 gap-3 mb-4">
                  <div>
                    <div className="text-2xl font-bold text-slate-800">
                      {(dataSummary.total_patents / 1000).toFixed(1)}k
                    </div>
                    <div className="text-[11px] text-slate-500">专利总量</div>
                  </div>
                  <div>
                    <div className="text-lg font-bold text-slate-800 mt-1">
                      {dataSummary.year_range[0]}-{dataSummary.year_range[1]}
                    </div>
                    <div className="text-[11px] text-slate-500">年份区间</div>
                  </div>
                </div>
                
                <div className="mb-3">
                  <div className="text-[11px] text-slate-500 mb-1.5">核心 IPC 分类</div>
                  <div className="flex flex-wrap gap-1.5">
                    {dataSummary.ipc_sections.map(ipc => (
                      <span key={ipc} className="bg-blue-50 text-blue-700 border border-blue-100 px-2 py-0.5 rounded text-[10px] font-mono font-medium">
                        {ipc}
                      </span>
                    ))}
                  </div>
                </div>
                
                <div>
                  <div className="text-[11px] text-slate-500 mb-1.5">主要申请人</div>
                  <div className="space-y-1">
                    {dataSummary.top_applicants.map(app => (
                      <div key={app.name} className="flex justify-between items-center text-xs">
                        <span className="text-slate-700 truncate pr-2" title={app.name}>{app.name}</span>
                        <span className="text-slate-400 font-mono">{app.count}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* LLM Settings Panel */}
          <div className="p-5">
            <h2 className="text-sm font-bold text-slate-800 uppercase tracking-wider mb-4 flex items-center gap-2">
              <Settings className="w-4 h-4 text-slate-500" /> LLM 设置
            </h2>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-slate-500 mb-1.5">大模型供应商</label>
                <select className="w-full px-3 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500">
                  <option>OpenAI (GPT-4)</option>
                  <option>Anthropic (Claude-3)</option>
                  <option>DeepSeek</option>
                  <option>Local (Ollama)</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-500 mb-1.5">API Key</label>
                <input 
                  type="password" 
                  value="sk-..." 
                  readOnly
                  className="w-full px-3 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none text-slate-400"
                />
              </div>
              <button className="w-full py-2 bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 text-sm font-medium rounded-lg shadow-sm transition-colors mt-2">
                测试连接
              </button>
            </div>
          </div>
        </aside>

        {/* --- Center: Chat Panel --- */}
        <section className="flex-1 flex flex-col bg-slate-50 relative">
          {/* Messages Area */}
          <div className="flex-1 overflow-y-auto p-4 md:p-6 lg:p-8 space-y-6">
            <div className="max-w-3xl mx-auto space-y-6 pb-20">
              {messages.map((msg) => (
                <MessageBubble key={msg.id} message={msg} />
              ))}
              <div ref={messagesEndRef} />
            </div>
          </div>

          {/* Input Area */}
          <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-slate-50 via-slate-50 to-transparent pt-10 pb-6 px-4 md:px-8">
            <div className="max-w-3xl mx-auto relative group">
              <div className="absolute -inset-1 bg-gradient-to-r from-blue-100 to-indigo-100 rounded-2xl blur opacity-25 group-hover:opacity-50 transition duration-1000 group-hover:duration-200"></div>
              <div className="relative flex items-end gap-2 bg-white rounded-2xl shadow-[0_2px_12px_rgba(0,0,0,0.06)] border border-slate-200 p-2 pl-4 transition-all focus-within:border-blue-300 focus-within:shadow-[0_4px_20px_rgba(59,130,246,0.1)]">
                <textarea
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleSendMessage();
                    }
                  }}
                  placeholder={dataSummary ? "描述你的分析需求，例如：分析锂电池技术的IPC分布趋势..." : "请先在左侧加载数据..."}
                  className="w-full max-h-32 min-h-[44px] py-3 text-sm text-slate-700 bg-transparent resize-none focus:outline-none"
                  disabled={isStreaming || !dataSummary}
                  rows={1}
                />
                <button
                  onClick={() => handleSendMessage()}
                  disabled={isStreaming || !inputText.trim() || !dataSummary}
                  className="mb-1 p-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white transition-colors disabled:opacity-50 disabled:hover:bg-blue-600 flex-shrink-0 shadow-sm shadow-blue-200"
                >
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </div>
            <div className="text-center mt-3 text-[11px] text-slate-400">
              PatentAgent Agent 会使用配置的 LLM 和内置分析工具来处理复杂意图。
            </div>
          </div>
        </section>

        {/* --- Right Sidebar: Quick Tools --- */}
        <aside className="w-[280px] bg-white border-l border-slate-200 overflow-y-auto flex flex-col shrink-0 shadow-[-4px_0_24px_rgba(0,0,0,0.02)] z-10">
          <div className="p-5 sticky top-0 bg-white/80 backdrop-blur-md border-b border-slate-100 z-20">
            <h2 className="text-sm font-bold text-slate-800 uppercase tracking-wider flex items-center gap-2">
              <Zap className="w-4 h-4 text-amber-500" /> 快捷工具
            </h2>
            <p className="text-xs text-slate-500 mt-1">一键触发标准分析流程</p>
          </div>
          
          <div className="p-4 space-y-1">
            {quickTools.map((tool) => {
              const Icon = tool.icon;
              return (
                <button
                  key={tool.name}
                  onClick={() => handleSendMessage(`请帮我执行: ${tool.name}`, tool.action)}
                  disabled={isStreaming || !dataSummary}
                  className="w-full flex items-center gap-3 p-3 rounded-xl hover:bg-slate-50 text-slate-700 transition-all hover:scale-[1.02] active:scale-[0.98] border border-transparent hover:border-slate-100 disabled:opacity-50 disabled:hover:scale-100 group"
                >
                  <div className="w-8 h-8 rounded-lg bg-indigo-50 flex items-center justify-center text-indigo-600 group-hover:bg-indigo-600 group-hover:text-white transition-colors">
                    <Icon className="w-4 h-4" />
                  </div>
                  <span className="text-sm font-medium">{tool.name}</span>
                </button>
              )
            })}
          </div>

          <div className="mt-auto p-5 border-t border-slate-100 bg-slate-50/50">
            <div className="bg-gradient-to-br from-indigo-50 to-blue-50 border border-indigo-100 p-4 rounded-xl relative overflow-hidden">
              <div className="absolute top-0 right-0 w-16 h-16 bg-blue-500 rounded-full blur-2xl opacity-10 transform translate-x-1/2 -translate-y-1/2"></div>
              <h3 className="text-sm font-bold text-indigo-900 mb-1">自定义流程?</h3>
              <p className="text-xs text-indigo-700/80 mb-3 leading-relaxed">
                在中央对话框输入您的具体业务需求，Agent会自动编排工具组合。
              </p>
            </div>
          </div>
        </aside>

      </main>
    </div>
  );
}