import { create } from "zustand";

interface OverlayStore {
  open: boolean;
  screen: string;
  entityId?: string;
  thinking: boolean;
  toggle: () => void;
  openFor: (screen: string, entityId?: string) => void;
  close: () => void;
  setThinking: (v: boolean) => void;
}

export const useOverlay = create<OverlayStore>((set) => ({
  open: false,
  screen: "chat",
  thinking: false,
  toggle: () => set((s) => ({ open: !s.open })),
  openFor: (screen, entityId) => set({ open: true, screen, entityId }),
  close: () => set({ open: false }),
  setThinking: (v) => set({ thinking: v }),
}));
