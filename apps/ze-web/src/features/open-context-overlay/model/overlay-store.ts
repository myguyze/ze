import { create } from "zustand";

interface OpenForExecutionParams {
  screen: string;
  entityId?: string;
  prefillMessage: string;
}

interface OverlayStore {
  open: boolean;
  screen: string;
  entityId?: string;
  prefillMessage?: string;
  toggle: () => void;
  openFor: (screen: string, entityId?: string) => void;
  openForExecution: (params: OpenForExecutionParams) => void;
  close: () => void;
  clearPrefill: () => void;
}

export const useOverlayStore = create<OverlayStore>((set) => ({
  open: false,
  screen: "chat",
  toggle: () => set((s) => ({ open: !s.open })),
  openFor: (screen, entityId) => set({ open: true, screen, entityId, prefillMessage: undefined }),
  openForExecution: ({ screen, entityId, prefillMessage }) =>
    set({ open: true, screen, entityId, prefillMessage }),
  close: () => set({ open: false }),
  clearPrefill: () => set({ prefillMessage: undefined }),
}));
