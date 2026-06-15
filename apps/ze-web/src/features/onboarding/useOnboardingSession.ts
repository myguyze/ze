import { create } from "zustand";

interface OnboardingSessionStore {
  sessionId: string | null;
  completed: boolean;
  setSession: (sessionId: string, completed: boolean) => void;
  clear: () => void;
}

export const useOnboardingSession = create<OnboardingSessionStore>((set) => ({
  sessionId: null,
  completed: false,
  setSession: (sessionId, completed) => {
    if (completed) {
      set({ sessionId: null, completed: true });
      return;
    }
    set({ sessionId, completed: false });
  },
  clear: () => set({ sessionId: null, completed: false }),
}));
