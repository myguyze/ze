import { create } from "zustand";

const THREAD_KEY = "ze_current_thread_id";

export function createThreadId(): string {
  return `ze-${crypto.randomUUID()}`;
}

function loadStoredThreadId(): string {
  const stored = localStorage.getItem(THREAD_KEY);
  if (stored) return stored;
  const id = createThreadId();
  localStorage.setItem(THREAD_KEY, id);
  return id;
}

interface SessionStore {
  threadId: string;
  highlightMessageId: string | null;
  newSession: () => string;
  selectSession: (id: string) => void;
  setHighlightMessage: (id: string | null) => void;
}

export const useSession = create<SessionStore>((set) => ({
  threadId: loadStoredThreadId(),
  highlightMessageId: null,
  newSession: () => {
    const id = createThreadId();
    localStorage.setItem(THREAD_KEY, id);
    set({ threadId: id });
    return id;
  },
  selectSession: (id) => {
    localStorage.setItem(THREAD_KEY, id);
    set({ threadId: id });
  },
  setHighlightMessage: (id) => {
    set({ highlightMessageId: id });
  },
}));
