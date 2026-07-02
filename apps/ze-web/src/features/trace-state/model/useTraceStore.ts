import type { WsTraceUpdateFrame } from "@myguyze/ze-client";
import { create } from "zustand";

function dedupeAppend(traces: WsTraceUpdateFrame[], trace: WsTraceUpdateFrame): WsTraceUpdateFrame[] {
  const without = traces.filter((t) => t.message_id !== trace.message_id);
  return [...without, trace];
}

function mergeOrdered(
  existing: WsTraceUpdateFrame[],
  incoming: WsTraceUpdateFrame[],
  orderedIds: string[],
): WsTraceUpdateFrame[] {
  const byId = new Map(existing.map((t) => [t.message_id, t]));
  for (const trace of incoming) {
    byId.set(trace.message_id, trace);
  }
  return orderedIds
    .map((id) => byId.get(id))
    .filter((t): t is WsTraceUpdateFrame => t !== undefined);
}

function tracesEqual(a: WsTraceUpdateFrame[], b: WsTraceUpdateFrame[]): boolean {
  if (a.length !== b.length) return false;
  return a.every((t, i) => t.message_id === b[i]?.message_id);
}

interface TraceState {
  traces: WsTraceUpdateFrame[];
  pending: boolean;
  pendingTrace: Partial<WsTraceUpdateFrame> | null;
  hydrating: boolean;
  appendTrace: (t: WsTraceUpdateFrame) => void;
  clearTraces: () => void;
  setPending: (v: boolean) => void;
  setHydrating: (v: boolean) => void;
  mergeTraces: (incoming: WsTraceUpdateFrame[], orderedIds: string[]) => void;
  mergePartialTrace: (fields: Partial<WsTraceUpdateFrame>) => void;
  commitPendingTrace: (final: WsTraceUpdateFrame) => void;
}

export const useTraceStore = create<TraceState>()((set) => ({
  traces: [],
  pending: false,
  pendingTrace: null,
  hydrating: false,
  appendTrace: (t) =>
    set((s) => ({ traces: dedupeAppend(s.traces, t), pending: false })),
  clearTraces: () => set({ traces: [], pending: false, pendingTrace: null, hydrating: false }),
  setPending: (v) => set({ pending: v }),
  setHydrating: (v) => set((s) => (s.hydrating === v ? s : { hydrating: v })),
  mergeTraces: (incoming, orderedIds) =>
    set((s) => {
      const merged = mergeOrdered(s.traces, incoming, orderedIds);
      if (tracesEqual(merged, s.traces) && !s.hydrating) return s;
      return { traces: merged, hydrating: false };
    }),
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
      traces: dedupeAppend(s.traces, final),
      pendingTrace: null,
      pending: false,
    })),
}));
