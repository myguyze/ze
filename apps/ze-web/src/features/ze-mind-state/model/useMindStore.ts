import type { WsTraceUpdateFrame } from "@ze/client";
import { create } from "zustand";
import { persist } from "zustand/middleware";

const MIN_WIDTH = 240;
const MAX_WIDTH = 480;

interface MindState {
  open: boolean;
  width: number;
  trace: WsTraceUpdateFrame | null;
  pending: boolean;
  toggle: () => void;
  setTrace: (t: WsTraceUpdateFrame) => void;
  setPending: (v: boolean) => void;
  setWidth: (w: number) => void;
}

export const useMindStore = create<MindState>()(
  persist(
    (set) => ({
      open: true,
      width: 320,
      trace: null,
      pending: false,
      toggle: () => set((s) => ({ open: !s.open })),
      setTrace: (t) => set({ trace: t, pending: false }),
      setPending: (v) => set({ pending: v }),
      setWidth: (w) => set({ width: Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, w)) }),
    }),
    {
      name: "ze-mind-panel",
      partialize: (s) => ({ open: s.open, width: s.width }),
    },
  ),
);
