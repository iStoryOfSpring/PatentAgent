import { useMutation } from "@tanstack/react-query";
import { exportReport } from "../../api";

export function useExportReportMutation() {
  return useMutation({
    mutationFn: (input: { messages: { role: string; content: string }[]; title: string }) =>
      exportReport(input.messages, input.title),
  });
}
