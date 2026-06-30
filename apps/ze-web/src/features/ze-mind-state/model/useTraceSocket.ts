import { useEffect } from "react";
import { useFrame, useWsStore } from "@/shared/api";
import { useSession } from "@/entities/session";
import { useMindStore } from "./useMindStore";

export function useTraceSocket() {
  const clearTraces = useMindStore((s) => s.clearTraces);
  const setPending = useMindStore((s) => s.setPending);
  const mergePartialTrace = useMindStore((s) => s.mergePartialTrace);
  const commitPendingTrace = useMindStore((s) => s.commitPendingTrace);
  const isThinking = useWsStore((s) => s.isThinking);
  const threadId = useSession((s) => s.threadId);

  useFrame("trace_update", (frame) => {
    if (frame.partial) {
      mergePartialTrace(frame);
    } else {
      commitPendingTrace(frame);
    }
  });

  useEffect(() => {
    clearTraces();
  }, [threadId, clearTraces]);

  useEffect(() => {
    setPending(isThinking);
  }, [isThinking, setPending]);
}
