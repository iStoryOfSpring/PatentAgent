import { useQuery } from "@tanstack/react-query";
import { fetchTools } from "../../api";

export const toolKeys = { all: ["tools"] as const };

export function useToolsQuery(enabled = true) {
  return useQuery({ queryKey: toolKeys.all, queryFn: fetchTools, enabled });
}
