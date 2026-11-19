import { useQuery } from "@tanstack/react-query";
import { ApiError, fetchDataSummary, fetchDatasets } from "../../api";

export const datasetKeys = {
  all: ["datasets"] as const,
  summary: ["datasets", "summary"] as const,
};

export function useDatasetsQuery() {
  return useQuery({ queryKey: datasetKeys.all, queryFn: fetchDatasets });
}

export function useDataSummaryQuery(enabled: boolean, sessionId?: string) {
  return useQuery({
    queryKey: [...datasetKeys.summary, sessionId ?? null],
    queryFn: async () => {
      try { return await fetchDataSummary(sessionId); }
      catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
    enabled,
  });
}
