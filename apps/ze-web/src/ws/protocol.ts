import type { ComponentDescriptor } from "@/components/types";
export type { ComponentDescriptor } from "@/components/types";

export interface Message {
  id: string;
  role: "user" | "assistant";
  text: string | null;
  components: ComponentDescriptor[];
  read: boolean;
  created_at: string;
  thread_id: string | null;
}

export interface ConfirmAction {
  label: string;
  value: string;
  style?: "primary" | "secondary" | "danger";
}

export interface ScreenContext {
  screen: string;
  goal_id?: string;
}

// ── Server → Client ───────────────────────────────────────────────────────────

export type InboundFrame =
  | { type: "message"; message: Message }
  | { type: "edit"; id: string; text?: string; components: ComponentDescriptor[] }
  | { type: "confirm_request"; id: string; prompt: string; actions: ConfirmAction[] }
  | { type: "confirm_cancel"; id: string }
  | { type: "typing" }
  | { type: "error"; detail: string }
  | { type: "refresh"; screen: string }
  | { type: "pong" };

// ── Client → Server ───────────────────────────────────────────────────────────

export type OutboundFrame =
  | { type: "message"; text: string; thread_id?: string; context?: ScreenContext }
  | { type: "ack"; ids: string[] }
  | { type: "command"; name: "cancel" | "costs" | "memory" | "contacts" }
  | { type: "ping" };
