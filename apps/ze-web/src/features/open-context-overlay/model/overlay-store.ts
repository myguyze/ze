import { create } from "zustand";

const OVERLAY_THREAD_KEY = "ze_overlay_thread_id";

function loadOverlayThreadId(): string {
  const stored = localStorage.getItem(OVERLAY_THREAD_KEY);
  if (stored) return stored;
  const id = `ze-${crypto.randomUUID()}`;
  localStorage.setItem(OVERLAY_THREAD_KEY, id);
  return id;
}

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
  overlayThreadId: string;
  toggle: () => void;
  setScreen: (screen: string, entityId?: string) => void;
  openFor: (screen: string, entityId?: string) => void;
  openForExecution: (params: OpenForExecutionParams) => void;
  close: () => void;
  clearPrefill: () => void;
  newOverlayThread: () => void;
}

export const useOverlayStore = create<OverlayStore>((set) => ({
  open: false,
  screen: "chat",
  overlayThreadId: loadOverlayThreadId(),
  toggle: () => set((s) => ({ open: !s.open })),
  setScreen: (screen, entityId) => set({ screen, entityId }),
  openFor: (screen, entityId) => set({ open: true, screen, entityId, prefillMessage: undefined }),
  openForExecution: ({ screen, entityId, prefillMessage }) =>
    set({ open: true, screen, entityId, prefillMessage }),
  close: () => set({ open: false }),
  clearPrefill: () => set({ prefillMessage: undefined }),
  newOverlayThread: () => {
    const id = `ze-${crypto.randomUUID()}`;
    localStorage.setItem(OVERLAY_THREAD_KEY, id);
    set({ overlayThreadId: id });
  },
}));
