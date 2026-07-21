import { useQuery } from "@tanstack/react-query";
import { fetchDataSummary, fetchDatasets } from "../../api";

export const datasetKeys = {
  all: ["datasets"] as const,
  summary: ["datasets", "summary"] as const,
};

export function useDatasetsQuery() {
  return useQuery({ queryKey: datasetKeys.all, queryFn: fetchDatasets });
}

export function useDataSummaryQuery(enabled: boolean) {
  return useQuery({ queryKey: datasetKeys.summary, queryFn: fetchDataSummary, enabled });
}
