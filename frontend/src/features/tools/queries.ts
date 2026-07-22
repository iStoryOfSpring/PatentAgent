import { useQuery } from "@tanstack/react-query";
import { fetchSearchStatus, fetchTools } from "../../api";

export const toolKeys = { all: ["tools"] as const };
export const searchStatusKey = ["search-status"] as const;

export function useToolsQuery(enabled = true) {
  return useQuery({ queryKey: toolKeys.all, queryFn: fetchTools, enabled });
}

export function useSearchStatusQuery(enabled = true) {
  return useQuery({ queryKey: searchStatusKey, queryFn: fetchSearchStatus, enabled });
}
