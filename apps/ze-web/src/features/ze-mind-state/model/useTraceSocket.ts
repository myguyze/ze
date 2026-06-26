import { useEffect } from "react";
import { useFrame, useWsStore } from "@/shared/api";
import { useMindStore } from "./useMindStore";

export function useTraceSocket() {
  const setTrace = useMindStore((s) => s.setTrace);
  const setPending = useMindStore((s) => s.setPending);
  const isThinking = useWsStore((s) => s.isThinking);

  useFrame("trace_update", (frame) => {
    setTrace(frame);
  });

  useEffect(() => {
    // set pending when thinking starts; clear it when thinking stops without a trace
    setPending(isThinking);
  }, [isThinking, setPending]);
}
