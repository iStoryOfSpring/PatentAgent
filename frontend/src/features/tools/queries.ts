import { useQuery } from "@tanstack/react-query";
import { fetchCapabilities, fetchSearchStatus, fetchTools } from "../../api";

export const toolKeys = { all: ["tools"] as const };
export const searchStatusKey = ["search-status"] as const;

export function useToolsQuery(enabled = true, sessionId?: string) {
  return useQuery({ queryKey: [...toolKeys.all, sessionId ?? null], queryFn: () => fetchTools(sessionId), enabled });
}

export function useSearchStatusQuery(enabled = true) {
  return useQuery({ queryKey: searchStatusKey, queryFn: fetchSearchStatus, enabled });
}

export function useCapabilitiesQuery(enabled = true, sessionId?: string) {
  return useQuery({queryKey:["capabilities", sessionId ?? null],queryFn:()=>fetchCapabilities(sessionId),enabled});
}
