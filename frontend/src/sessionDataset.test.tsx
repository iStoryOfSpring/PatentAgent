// @vitest-environment jsdom
import { act,cleanup,fireEvent,render,screen,waitFor } from "@testing-library/react";
import { QueryClient,QueryClientProvider } from "@tanstack/react-query";
import { afterEach,beforeEach,expect,it,vi } from "vitest";
import App from "./App";
import { fetchTools,fetchCapabilities,fetchDataSummary } from "./api";

const clients:QueryClient[]=[];
function response(body:unknown,status=200){return new Response(JSON.stringify(body),{status,headers:{"Content-Type":"application/json"}});}
function deferred<T>(){let resolve!:(value:T)=>void;const promise=new Promise<T>(r=>{resolve=r;});return {promise,resolve};}
function fixture(){
  let bound="version_A";
  const calls:string[]=[];
  const sessions=()=>[{id:"session_a",name:"Session A",dataset_version_id:bound},{id:"session_b",name:"Session B",dataset_version_id:"version_B"}];
  const tools=(id:string)=>({tools:[{name:"get_dataset_summary",parameters:{},description:id,availability:{available:id!=="session_b",reason:id==="session_b"?"B unavailable":""}}]});
  const summary=(id:string)=>({total_patents:id==="session_b" || bound==="version_B"?2:1,year_range:[2020,2021],ipc_sections:[],top_applicants:[]});
  const versions=[{id:"version_B",dataset_id:"dataset_B",record_count:2,content_hash:"hash_B",sources:[],field_coverage:{},schema_version:4}];
  const defaultFetch=async(input:RequestInfo|URL,init?:RequestInit)=>{
    const value=String(input);calls.push(value);const url=new URL(value,"http://localhost");const id=url.searchParams.get("session_id") || "default";
    if(url.pathname==="/api/health")return response({status:"ok",patents_loaded:0,agent_configured:false,tools:1,dataset_snapshot:{version_id:"version_default"}});
    if(url.pathname==="/api/sessions")return response({sessions:sessions()});
    if(url.pathname==="/api/sessions/session_a/dataset"){bound=JSON.parse(String(init?.body)).dataset_version_id;return response({session:sessions()[0],stale_evidence_count:0});}
    if(url.pathname.startsWith("/api/sessions/"))return response({session:sessions().find(s=>url.pathname.endsWith(s.id)),messages:[],turns:[],tool_executions:[]});
    if(url.pathname==="/api/tools")return response(tools(id));
    if(url.pathname==="/api/data/summary")return response(summary(id));
    if(url.pathname==="/api/capabilities")return response({capabilities:[]});
    if(url.pathname==="/api/datasets")return response({datasets:[{id:"dataset_B",name:"Dataset B",status:"ready",latest_version:versions[0],version_count:1}]});
    if(url.pathname.endsWith("/versions"))return response({versions});
    if(url.pathname==="/api/sources")return response({sources:[]});
    if(url.pathname==="/api/llm/profiles")return response({profiles:[]});
    if(url.pathname==="/api/search/status")return response({dependency_installed:false,index_count:0,modes:["lexical"]});
    throw new Error("unexpected test request: "+value);
  };
  return {calls,defaultFetch,tools,summary};
}
function mount(){const client=new QueryClient({defaultOptions:{queries:{retry:false,staleTime:10000,refetchOnWindowFocus:false}}});clients.push(client);render(<QueryClientProvider client={client}><App/></QueryClientProvider>);return client;}
beforeEach(()=>{
  const values=new Map<string,string>([["patentagent_session_id","session_a"]]);const storage={getItem:(k:string)=>values.get(k)||null,setItem:(k:string,v:string)=>values.set(k,v),removeItem:(k:string)=>values.delete(k)};
  Object.defineProperty(window,"localStorage",{configurable:true,value:storage});Object.defineProperty(globalThis,"localStorage",{configurable:true,value:storage});
  window.history.replaceState({},"","/capabilities");HTMLElement.prototype.scrollIntoView=vi.fn();vi.spyOn(window,"confirm").mockReturnValue(true);
});
afterEach(()=>{cleanup();clients.splice(0).forEach(c=>c.clear());vi.restoreAllMocks();vi.unstubAllGlobals();});

it("encodes optional session selectors while preserving no-parameter requests",async()=>{
  const calls:string[]=[];vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL)=>{calls.push(String(input));return response({tools:[],capabilities:[]});}));
  await fetchTools();await fetchCapabilities();await fetchDataSummary();
  await fetchTools("session a&b");await fetchCapabilities("session a&b");await fetchDataSummary("session a&b");
  expect(calls).toEqual(["/api/tools","/api/capabilities","/api/data/summary","/api/tools?session_id=session%20a%26b","/api/capabilities?session_id=session%20a%26b","/api/data/summary?session_id=session%20a%26b"]);
});

it("restores a bound session with default health zero and refetches it after explicit rebind",async()=>{
  const f=fixture();vi.stubGlobal("fetch",vi.fn(f.defaultFetch));mount();
  await waitFor(()=>expect(screen.getByRole("button",{name:"数据总览"}).hasAttribute("disabled")).toBe(false));
  fireEvent.click(screen.getByRole("button",{name:"智能分析"}));
  await screen.findByText("1 件 · 2020–2021");
  expect(f.calls).toContain("/api/data/summary?session_id=session_a");
  expect(f.calls).not.toContain("/api/data/summary");
  fireEvent.click(screen.getByRole("button",{name:"数据集"}));
  fireEvent.click(await screen.findByRole("button",{name:"绑定会话"}));
  fireEvent.click(screen.getByRole("button",{name:"智能分析"}));
  await screen.findByText("2 件 · 2020–2021");
  expect(f.calls.filter(url=>url==="/api/tools?session_id=session_a").length).toBeGreaterThan(1);
  expect(f.calls.filter(url=>url==="/api/capabilities?session_id=session_a").length).toBeGreaterThan(1);
});

it("late responses from session A cannot overwrite session B availability or summary",async()=>{
  const f=fixture();const pending=new Map<string,ReturnType<typeof deferred<Response>>>();
  vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
    const value=String(input);
    if(["/api/tools","/api/data/summary","/api/capabilities"].some(path=>value===path+"?session_id=session_a")){const wait=deferred<Response>();pending.set(value,wait);return wait.promise;}
    return f.defaultFetch(input,init);
  }));
  const client=mount();await waitFor(()=>expect(pending.size).toBe(3));
  fireEvent.click(screen.getByRole("button",{name:"智能分析"}));
  fireEvent.click(screen.getByText("Session B"));
  await screen.findByText("2 件 · 2020–2021");
  fireEvent.click(screen.getByRole("button",{name:"能力与工具"}));
  expect(screen.getByRole("button",{name:"数据总览"}).hasAttribute("disabled")).toBe(true);
  await act(async()=>{for(const [url,wait] of pending){wait.resolve(response(url.startsWith("/api/tools")?f.tools("session_a"):url.startsWith("/api/data")?f.summary("session_a"):{capabilities:[]}));}await Promise.resolve();});
  await waitFor(()=>expect(client.getQueryData(["tools","session_a"])).toBeTruthy());
  expect(screen.getByRole("button",{name:"数据总览"}).hasAttribute("disabled")).toBe(true);
  fireEvent.click(screen.getByRole("button",{name:"智能分析"}));
  expect(screen.getByText("2 件 · 2020–2021")).toBeTruthy();
});

it("404 summary is an empty state and 409 invalidation removes cached usable tools",async()=>{
  const f=fixture();let state=200;
  vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
    const url=String(input);
    if(state!==200 && url.startsWith("/api/data/summary?"))return response({detail:state===404?"unbound":"requires_reimport: conflict"},state);
    if(state===409 && (url.startsWith("/api/tools?")||url.startsWith("/api/capabilities?")))return response({detail:"requires_reimport: conflict"},409);
    return f.defaultFetch(input,init);
  }));
  const client=mount();fireEvent.click(screen.getByRole("button",{name:"智能分析"}));await screen.findByText("1 件 · 2020–2021");
  state=404;await act(async()=>{await client.invalidateQueries({queryKey:["datasets","summary"]});});
  expect(screen.queryByText(/requires_reimport/)).toBeNull();expect(await screen.findByText("尚未加载数据")).toBeTruthy();
  state=409;await act(async()=>{await Promise.all([client.invalidateQueries({queryKey:["tools"]}),client.invalidateQueries({queryKey:["capabilities"]}),client.invalidateQueries({queryKey:["datasets","summary"]})]);});
  expect(await screen.findByText(/requires_reimport: conflict/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button",{name:"能力与工具"}));
  expect(screen.queryByRole("button",{name:"数据总览"})).toBeNull();
  expect(screen.queryByText("1 件 · 2020–2021")).toBeNull();
});

it("does not switch sessions while a quick tool result is pending",async()=>{
  const f=fixture();const result=deferred<Response>();
  vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>String(input)==="/api/tools/get_dataset_summary"?result.promise:f.defaultFetch(input,init)));
  mount();const run=await screen.findByRole("button",{name:"数据总览"});await waitFor(()=>expect(run.hasAttribute("disabled")).toBe(false));
  fireEvent.click(run);
  fireEvent.click(screen.getByRole("button",{name:"智能分析"}));
  const other=screen.getByText("Session B").closest("button")!;expect(other.disabled).toBe(true);fireEvent.click(other);
  await act(async()=>{result.resolve(response({result_type:"dataset_summary",total_patents:1,summary:"Saved A result",result_metadata:{execution_id:"execA"},warnings:[]}));});
  expect(window.localStorage.getItem("patentagent_session_id")).toBe("session_a");
});
