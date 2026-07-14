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
  | WsPongFrame
  | WsTraceUpdateFrame
  | WsNotificationFrame;
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
export type ThreadId1 = string | null;
export type Text1 = string | null;
export type Components1 = {
  [k: string]: unknown;
}[];
export type Type2 = "confirm_request";
export type Id2 = string;
export type ThreadId2 = string | null;
export type Prompt = string;
export type Label = string;
export type Value = string;
export type Style = ("primary" | "secondary" | "danger") | null;
export type Actions = WsConfirmAction[];
export type Type3 = "confirm_cancel";
export type Id3 = string;
export type ThreadId3 = string | null;
export type Type4 = "typing";
export type ThreadId4 = string | null;
export type Text2 = string | null;
export type Type5 = "token";
export type ThreadId5 = string | null;
export type Text3 = string;
export type Type6 = "error";
export type ThreadId6 = string | null;
export type Detail = string;
export type Type7 = "refresh";
export type ThreadId7 = string | null;
export type Screen = string;
export type Type8 = "pong";
export type Type9 = "trace_update";
export type ThreadId8 = string | null;
export type MessageId = string;
export type Partial = boolean;
export type Agent = string;
export type RoutingMethod = string;
export type Confidence = number;
export type ScoreGap = number;
export type IsCompound = boolean;
export type Subtasks = string[];
export type Text4 = string;
export type Score = number;
export type Source = string;
export type ExtractionConfidence = number | null;
export type MemoryChunks = MemoryChunkTraceResponse[];
export type Name = string;
export type ResultSnippet = string;
export type DurationMs = number;
export type Success = boolean;
export type ToolCalls = ToolCallTraceResponse[];
export type TotalDurationMs = number;
export type Type10 = "notification";
export type Id4 = string;
export type EventType = string;
export type Source1 = string;
export type Title = string;
export type Body = string;
export type TargetType = string | null;
export type TargetId = string | null;
export type CreatedAt1 = string;
export type Read1 = boolean;
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
export type Type11 = "message";
export type Text5 = string;
export type ThreadId9 = string | null;
export type Screen1 = string;
export type GoalId = string | null;
export type WorkflowId = string | null;
export type ExecutionId = string | null;
export type Type12 = "ack";
export type Ids = string[];
export type Type13 = "confirm";
export type Id5 = string;
export type ThreadId10 = string;
export type Choice = "approve" | "deny";
export type Type14 = "action";
export type Payload = string;
export type ThreadId11 = string | null;
export type Type15 = "command";
export type Name1 = "cancel" | "costs" | "capabilities" | "status" | "onboarding" | "reset" | "reset_preview";
export type Type16 = "component_submit";
export type StepId = string;
export type SessionId1 = string | null;
export type ThreadId12 = string | null;
export type Type17 = "ping";

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
  thread_id?: ThreadId1;
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
  thread_id?: ThreadId2;
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
  thread_id?: ThreadId3;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsTypingFrame".
 */
export interface WsTypingFrame {
  type: Type4;
  thread_id?: ThreadId4;
  text?: Text2;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsTokenFrame".
 */
export interface WsTokenFrame {
  type: Type5;
  thread_id?: ThreadId5;
  text: Text3;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsErrorFrame".
 */
export interface WsErrorFrame {
  type: Type6;
  thread_id?: ThreadId6;
  detail: Detail;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsRefreshFrame".
 */
export interface WsRefreshFrame {
  type: Type7;
  thread_id?: ThreadId7;
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
 * via the `definition` "WsTraceUpdateFrame".
 */
export interface WsTraceUpdateFrame {
  type: Type9;
  thread_id?: ThreadId8;
  message_id: MessageId;
  partial?: Partial;
  agent: Agent;
  routing_method: RoutingMethod;
  confidence: Confidence;
  score_gap: ScoreGap;
  is_compound: IsCompound;
  subtasks: Subtasks;
  memory_chunks: MemoryChunks;
  tool_calls: ToolCalls;
  total_duration_ms: TotalDurationMs;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "MemoryChunkTraceResponse".
 */
export interface MemoryChunkTraceResponse {
  text: Text4;
  score: Score;
  source: Source;
  extraction_confidence?: ExtractionConfidence;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "ToolCallTraceResponse".
 */
export interface ToolCallTraceResponse {
  name: Name;
  result_snippet: ResultSnippet;
  duration_ms: DurationMs;
  success: Success;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsNotificationFrame".
 */
export interface WsNotificationFrame {
  type: Type10;
  id: Id4;
  event_type: EventType;
  source: Source1;
  title: Title;
  body: Body;
  target_type: TargetType;
  target_id: TargetId;
  created_at: CreatedAt1;
  read?: Read1;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsSendMessageFrame".
 */
export interface WsSendMessageFrame {
  type: Type11;
  text: Text5;
  thread_id?: ThreadId9;
  context?: WsScreenContext | null;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsScreenContext".
 */
export interface WsScreenContext {
  screen: Screen1;
  goal_id?: GoalId;
  workflow_id?: WorkflowId;
  execution_id?: ExecutionId;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsAckFrame".
 */
export interface WsAckFrame {
  type: Type12;
  ids: Ids;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsConfirmFrame".
 */
export interface WsConfirmFrame {
  type: Type13;
  id: Id5;
  thread_id: ThreadId10;
  choice: Choice;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsActionFrame".
 */
export interface WsActionFrame {
  type: Type14;
  payload: Payload;
  thread_id?: ThreadId11;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsCommandFrame".
 */
export interface WsCommandFrame {
  type: Type15;
  name: Name1;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsComponentSubmitFrame".
 */
export interface WsComponentSubmitFrame {
  type: Type16;
  step_id: StepId;
  values: Values;
  session_id?: SessionId1;
  thread_id?: ThreadId12;
}
export interface Values {
  [k: string]: unknown;
}
/**
 * This interface was referenced by `WsProtocol`'s JSON-Schema
 * via the `definition` "WsPingFrame".
 */
export interface WsPingFrame {
  type: Type17;
}
