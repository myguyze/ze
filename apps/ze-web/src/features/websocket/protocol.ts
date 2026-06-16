import type { ComponentDescriptor } from "@/components/server-driven/types";
export type { ComponentDescriptor } from "@/components/server-driven/types";

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

export interface OnboardingMeta {
  session_id: string;
  completed: boolean;
}

export type InboundFrame =
  | { type: "message"; message: Message; onboarding?: OnboardingMeta }
  | { type: "edit"; id: string; text?: string; components: ComponentDescriptor[] }
  | { type: "confirm_request"; id: string; prompt: string; actions: ConfirmAction[] }
  | { type: "confirm_cancel"; id: string }
  | { type: "typing"; text?: string }
  | { type: "token"; text: string }
  | { type: "error"; detail: string }
  | { type: "refresh"; screen: string }
  | { type: "pong" };

// ── Client → Server ───────────────────────────────────────────────────────────

export type OutboundFrame =
  | { type: "message"; text: string; thread_id?: string; context?: ScreenContext }
  | { type: "ack"; ids: string[] }
  | { type: "confirm"; id: string; choice: "approve" | "deny" }
  | { type: "command"; name: "cancel" | "costs" | "capabilities" | "status" | "onboarding" | "reset" | "reset_preview" }
  | { type: "component_submit"; step_id: string; values: Record<string, unknown>; session_id?: string; thread_id?: string }
  | { type: "ping" };
