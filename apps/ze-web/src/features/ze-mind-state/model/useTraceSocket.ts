import { useEffect } from "react";
import { useFrame, useWsStore } from "@/shared/api";
import { useSession } from "@/entities/session";
import { useMindStore } from "./useMindStore";

export function useTraceSocket() {
  const appendTrace = useMindStore((s) => s.appendTrace);
  const clearTraces = useMindStore((s) => s.clearTraces);
  const setPending = useMindStore((s) => s.setPending);
  const isThinking = useWsStore((s) => s.isThinking);
  const threadId = useSession((s) => s.threadId);

  useFrame("trace_update", (frame) => {
    appendTrace(frame);
  });

  // clear thread when session changes
  useEffect(() => {
    clearTraces();
  }, [threadId, clearTraces]);

  // set pending when thinking starts; clear it if thinking stops without a trace
  useEffect(() => {
    setPending(isThinking);
  }, [isThinking, setPending]);
}
