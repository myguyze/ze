import { create } from "zustand";
import { persist } from "zustand/middleware";

const MIN_WIDTH = 240;
const MAX_WIDTH = 480;

export type ChatSidePanelTab = "trace" | "history";

interface ChatSidePanelState {
  open: boolean;
  width: number;
  tab: ChatSidePanelTab;
  toggleTab: (tab: ChatSidePanelTab) => void;
  setTab: (tab: ChatSidePanelTab) => void;
  setOpen: (open: boolean) => void;
  setWidth: (w: number) => void;
}

export const useChatSidePanelStore = create<ChatSidePanelState>()(
  persist(
    (set) => ({
      open: true,
      width: 320,
      tab: "trace",
      toggleTab: (tab) =>
        set((s) => {
          if (s.open && s.tab === tab) return { open: false };
          return { open: true, tab };
        }),
      setTab: (tab) => set({ tab, open: true }),
      setOpen: (open) => set({ open }),
      setWidth: (w) => set({ width: Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, w)) }),
    }),
    {
      name: "ze-chat-side-panel",
      partialize: (s) => ({ open: s.open, width: s.width, tab: s.tab }),
      merge: (persisted, current) => {
        const saved = persisted as Partial<ChatSidePanelState> | undefined;
        const tab =
          (saved?.tab as string | undefined) === "mind" ? "trace" : saved?.tab;
        return { ...current, ...saved, tab: tab ?? current.tab };
      },
    },
  ),
);
