import { useQuery } from "@tanstack/react-query";
import { fetchHealth, fetchProviderProfiles } from "../../api";

export const providerKeys = {
  health: ["providers", "health"] as const,
  profiles: ["providers", "profiles"] as const,
};

export function useHealthQuery() {
  return useQuery({ queryKey: providerKeys.health, queryFn: fetchHealth });
}

export function useProviderProfilesQuery(enabled = true) {
  return useQuery({ queryKey: providerKeys.profiles, queryFn: fetchProviderProfiles, enabled });
}
