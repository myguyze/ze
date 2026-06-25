import { create } from "zustand";

interface NoticeStore {
  notice: string | null;
  showNotice: (message: string) => void;
  clearNotice: () => void;
}

export const useSendNotice = create<NoticeStore>((set) => ({
  notice: null,
  showNotice: (message) => set({ notice: message }),
  clearNotice: () => set({ notice: null }),
}));
