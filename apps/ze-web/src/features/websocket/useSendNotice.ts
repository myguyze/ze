import { create } from "zustand";

interface SendNoticeStore {
  notice: string | null;
  showNotice: (message: string) => void;
  clearNotice: () => void;
}

export const useSendNotice = create<SendNoticeStore>((set) => ({
  notice: null,
  showNotice: (message) => set({ notice: message }),
  clearNotice: () => set({ notice: null }),
}));
