import { useQuery } from "@tanstack/react-query";
import { fetchSession, fetchSessions } from "../../api";

export const sessionKeys = {
  all: ["sessions"] as const,
  detail: (id: string) => ["sessions", id] as const,
};

export function useSessionsQuery() {
  return useQuery({ queryKey: sessionKeys.all, queryFn: fetchSessions });
}

export function useSessionQuery(id: string) {
  return useQuery({ queryKey: sessionKeys.detail(id), queryFn: () => fetchSession(id), enabled: Boolean(id) });
}
