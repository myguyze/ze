/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsInboundFrame".
 */
export type WsInboundFrame =
  | WsMessageFrame
  | WsEditFrame
  | WsConfirmRequestFrame
  | WsConfirmCancelFrame
  | WsTypingFrame
  | WsTokenFrame
  | WsErrorFrame
  | WsRefreshFrame
  | WsPongFrame;
export type Type = "message";
export type Id = string;
export type Role = "user" | "assistant";
export type Text = string | null;
export type Components = {
  [k: string]: unknown;
}[];
export type Read = boolean;
export type ThreadId = string | null;
export type CreatedAt = string;
export type SessionId = string;
export type Completed = boolean;
export type Type1 = "edit";
export type Id1 = string;
export type Text1 = string | null;
export type Components1 = {
  [k: string]: unknown;
}[];
export type Type2 = "confirm_request";
export type Id2 = string;
export type Prompt = string;
export type Label = string;
export type Value = string;
export type Style = ("primary" | "secondary" | "danger") | null;
export type Actions = WsConfirmAction[];
export type Type3 = "confirm_cancel";
export type Id3 = string;
export type Type4 = "typing";
export type Text2 = string | null;
export type Type5 = "token";
export type Text3 = string;
export type Type6 = "error";
export type Detail = string;
export type Type7 = "refresh";
export type Screen = string;
export type Type8 = "pong";
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsOutboundFrame".
 */
export type WsOutboundFrame =
  | WsSendMessageFrame
  | WsAckFrame
  | WsConfirmFrame
  | WsActionFrame
  | WsCommandFrame
  | WsComponentSubmitFrame
  | WsPingFrame;
export type Type9 = "message";
export type Text4 = string;
export type ThreadId1 = string | null;
export type Screen1 = string;
export type GoalId = string | null;
export type Type10 = "ack";
export type Ids = string[];
export type Type11 = "confirm";
export type Id4 = string;
export type Choice = "approve" | "deny";
export type Type12 = "action";
export type Payload = string;
export type Type13 = "command";
export type Name = "cancel" | "costs" | "capabilities" | "status" | "onboarding" | "reset" | "reset_preview";
export type Type14 = "component_submit";
export type StepId = string;
export type SessionId1 = string | null;
export type ThreadId2 = string | null;
export type Type15 = "ping";

export interface WsProtocol {
  inbound?: WsInboundFrame;
  outbound?: WsOutboundFrame;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsMessageFrame".
 */
export interface WsMessageFrame {
  type: Type;
  message: MessageSchema;
  onboarding?: OnboardingMeta | null;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "MessageSchema".
 */
export interface MessageSchema {
  id: Id;
  role: Role;
  text: Text;
  components: Components;
  read: Read;
  thread_id: ThreadId;
  created_at: CreatedAt;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "OnboardingMeta".
 */
export interface OnboardingMeta {
  session_id: SessionId;
  completed: Completed;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsEditFrame".
 */
export interface WsEditFrame {
  type: Type1;
  id: Id1;
  text?: Text1;
  components?: Components1;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsConfirmRequestFrame".
 */
export interface WsConfirmRequestFrame {
  type: Type2;
  id: Id2;
  prompt: Prompt;
  actions: Actions;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsConfirmAction".
 */
export interface WsConfirmAction {
  label: Label;
  value: Value;
  style?: Style;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsConfirmCancelFrame".
 */
export interface WsConfirmCancelFrame {
  type: Type3;
  id: Id3;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsTypingFrame".
 */
export interface WsTypingFrame {
  type: Type4;
  text?: Text2;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsTokenFrame".
 */
export interface WsTokenFrame {
  type: Type5;
  text: Text3;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsErrorFrame".
 */
export interface WsErrorFrame {
  type: Type6;
  detail: Detail;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsRefreshFrame".
 */
export interface WsRefreshFrame {
  type: Type7;
  screen: Screen;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsPongFrame".
 */
export interface WsPongFrame {
  type: Type8;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsSendMessageFrame".
 */
export interface WsSendMessageFrame {
  type: Type9;
  text: Text4;
  thread_id?: ThreadId1;
  context?: WsScreenContext | null;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsScreenContext".
 */
export interface WsScreenContext {
  screen: Screen1;
  goal_id?: GoalId;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsAckFrame".
 */
export interface WsAckFrame {
  type: Type10;
  ids: Ids;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsConfirmFrame".
 */
export interface WsConfirmFrame {
  type: Type11;
  id: Id4;
  choice: Choice;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsActionFrame".
 */
export interface WsActionFrame {
  type: Type12;
  payload: Payload;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsCommandFrame".
 */
export interface WsCommandFrame {
  type: Type13;
  name: Name;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsComponentSubmitFrame".
 */
export interface WsComponentSubmitFrame {
  type: Type14;
  step_id: StepId;
  values: Values;
  session_id?: SessionId1;
  thread_id?: ThreadId2;
}
export interface Values {
  [k: string]: unknown;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsPingFrame".
 */
export interface WsPingFrame {
  type: Type15;
}
