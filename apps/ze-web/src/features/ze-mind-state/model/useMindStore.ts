import type { WsTraceUpdateFrame } from "@myguyze/ze-client";
import { create } from "zustand";
import { persist } from "zustand/middleware";

const MIN_WIDTH = 240;
const MAX_WIDTH = 480;

interface MindState {
  open: boolean;
  width: number;
  traces: WsTraceUpdateFrame[];
  pending: boolean;
  pendingTrace: Partial<WsTraceUpdateFrame> | null;
  toggle: () => void;
  appendTrace: (t: WsTraceUpdateFrame) => void;
  clearTraces: () => void;
  setPending: (v: boolean) => void;
  mergePartialTrace: (fields: Partial<WsTraceUpdateFrame>) => void;
  commitPendingTrace: (final: WsTraceUpdateFrame) => void;
  setWidth: (w: number) => void;
}

export const useMindStore = create<MindState>()(
  persist(
    (set) => ({
      open: true,
      width: 320,
      traces: [],
      pending: false,
      pendingTrace: null,
      toggle: () => set((s) => ({ open: !s.open })),
      appendTrace: (t) => set((s) => ({ traces: [...s.traces, t], pending: false })),
      clearTraces: () => set({ traces: [], pending: false, pendingTrace: null }),
      setPending: (v) => set({ pending: v }),
      mergePartialTrace: (fields) =>
        set((s) => {
          const base = s.pendingTrace ?? {};
          const { memory_chunks: newChunks = [], tool_calls: newCalls = [], ...rest } = fields;
          return {
            pendingTrace: {
              ...base,
              ...rest,
              memory_chunks: [...(base.memory_chunks ?? []), ...newChunks],
              tool_calls: [...(base.tool_calls ?? []), ...newCalls],
            },
          };
        }),
      commitPendingTrace: (final) =>
        set((s) => ({
          traces: [...s.traces, final],
          pendingTrace: null,
          pending: false,
        })),
      setWidth: (w) => set({ width: Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, w)) }),
    }),
    {
      name: "ze-mind-panel",
      partialize: (s) => ({ open: s.open, width: s.width }),
    },
  ),
);
