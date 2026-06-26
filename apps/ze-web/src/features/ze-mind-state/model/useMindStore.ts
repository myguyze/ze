import type { WsTraceUpdateFrame } from "@ze/client";
import { create } from "zustand";
import { persist } from "zustand/middleware";

const MIN_WIDTH = 240;
const MAX_WIDTH = 480;

interface MindState {
  open: boolean;
  width: number;
  traces: WsTraceUpdateFrame[];
  pending: boolean;
  toggle: () => void;
  appendTrace: (t: WsTraceUpdateFrame) => void;
  clearTraces: () => void;
  setPending: (v: boolean) => void;
  setWidth: (w: number) => void;
}

export const useMindStore = create<MindState>()(
  persist(
    (set) => ({
      open: true,
      width: 320,
      traces: [],
      pending: false,
      toggle: () => set((s) => ({ open: !s.open })),
      appendTrace: (t) => set((s) => ({ traces: [...s.traces, t], pending: false })),
      clearTraces: () => set({ traces: [], pending: false }),
      setPending: (v) => set({ pending: v }),
      setWidth: (w) => set({ width: Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, w)) }),
    }),
    {
      name: "ze-mind-panel",
      partialize: (s) => ({ open: s.open, width: s.width }),
    },
  ),
);
