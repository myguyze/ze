import { useEffect } from "react";
import { useSession } from "@/entities/session";
import { useFrame, useWsStore } from "@/shared/api";
import { useTraceStore } from "./useTraceStore";

export function useTraceSocket() {
  const setPending = useTraceStore((s) => s.setPending);
  const mergePartialTrace = useTraceStore((s) => s.mergePartialTrace);
  const commitPendingTrace = useTraceStore((s) => s.commitPendingTrace);
  const threadId = useSession((s) => s.threadId);
  const isThinking = useWsStore((s) => s.thinkingThreads[threadId] ?? false);

  useFrame("trace_update", (frame) => {
    if (frame.partial) {
      mergePartialTrace(frame);
    } else {
      commitPendingTrace(frame);
    }
  });

  useEffect(() => {
    setPending(isThinking);
  }, [isThinking, setPending]);
}
