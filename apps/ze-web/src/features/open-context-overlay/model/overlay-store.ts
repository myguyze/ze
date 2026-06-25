import { create } from "zustand";

interface OverlayStore {
  open: boolean;
  screen: string;
  entityId?: string;
  toggle: () => void;
  openFor: (screen: string, entityId?: string) => void;
  close: () => void;
}

export const useOverlayStore = create<OverlayStore>((set) => ({
  open: false,
  screen: "chat",
  toggle: () => set((s) => ({ open: !s.open })),
  openFor: (screen, entityId) => set({ open: true, screen, entityId }),
  close: () => set({ open: false }),
}));
