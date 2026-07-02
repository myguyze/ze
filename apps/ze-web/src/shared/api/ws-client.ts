import type { WsInboundFrame as InboundFrame, WsOutboundFrame as OutboundFrame } from "@myguyze/ze-client";
import { useEffect, useRef } from "react";
import { create } from "zustand";
import { getConfig } from "@/shared/config";

interface WsStore {
  isConnected: boolean;
  thinkingThreads: Record<string, boolean>;
  typingTextThreads: Record<string, string | null>;
  attentionThreads: Record<string, boolean>;
  setConnected: (v: boolean) => void;
  setThreadThinking: (threadId: string, v: boolean) => void;
  setThreadTypingText: (threadId: string, text: string | null) => void;
  setThreadAttention: (threadId: string, v: boolean) => void;
}

export const useWsStore = create<WsStore>((set) => ({
  isConnected: false,
  thinkingThreads: {},
  typingTextThreads: {},
  attentionThreads: {},
  setConnected: (v) => set({ isConnected: v }),
  setThreadThinking: (threadId, v) =>
    set((s) => ({ thinkingThreads: { ...s.thinkingThreads, [threadId]: v } })),
  setThreadTypingText: (threadId, text) =>
    set((s) => ({ typingTextThreads: { ...s.typingTextThreads, [threadId]: text } })),
  setThreadAttention: (threadId, v) =>
    set((s) => ({ attentionThreads: { ...s.attentionThreads, [threadId]: v } })),
}));

type FrameType = InboundFrame["type"];
const frameHandlers = new Map<FrameType, Set<(f: InboundFrame) => void>>();

function dispatch(frame: InboundFrame) {
  frameHandlers.get(frame.type)?.forEach((h) => h(frame));
}

let ws: WebSocket | null = null;
let retryTimeout: ReturnType<typeof setTimeout> | null = null;
let retryDelay = 1000;
let pingInterval: ReturnType<typeof setInterval> | null = null;

function buildUrl() {
  const cfg = getConfig();
  if (!cfg) return null;
  const base = cfg.serverUrl.replace(/^http/, "ws");
  return `${base}/ws?token=${encodeURIComponent(cfg.apiKey)}`;
}

function scheduleReconnect() {
  if (retryTimeout) return;
  retryTimeout = setTimeout(() => {
    retryTimeout = null;
    connect();
  }, retryDelay);
  retryDelay = Math.min(retryDelay * 2, 30_000);
}

function connect() {
  const url = buildUrl();
  if (!url) return;

  ws = new WebSocket(url);

  ws.onopen = () => {
    retryDelay = 1000;
    // Clear stale per-thread state — any in-flight requests from the previous
    // connection are gone, so the backend is no longer busy.
    useWsStore.setState({ thinkingThreads: {}, typingTextThreads: {}, isConnected: true });
    pingInterval = setInterval(() => send({ type: "ping" }), 30_000);
  };

  ws.onmessage = (event) => {
    let frame: InboundFrame;
    try {
      frame = JSON.parse(event.data as string) as InboundFrame;
    } catch {
      return;
    }
    dispatch(frame);
  };

  ws.onclose = () => {
    ws = null;
    useWsStore.getState().setConnected(false);
    if (pingInterval) clearInterval(pingInterval);
    scheduleReconnect();
  };

  ws.onerror = () => {
    ws?.close();
  };
}

export function send(frame: OutboundFrame): boolean {
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(frame));
    return true;
  }
  return false;
}

export function reconnect() {
  if (retryTimeout) {
    clearTimeout(retryTimeout);
    retryTimeout = null;
  }
  ws?.close();
  retryDelay = 1000;
  connect();
}

export function useFrame<T extends FrameType>(
  type: T,
  handler: (f: Extract<InboundFrame, { type: T }>) => void,
) {
  const ref = useRef(handler);
  // Keep handler ref fresh without re-subscribing the frame listener.
  // eslint-disable-next-line react-hooks/refs -- intentional stable-subscription pattern
  ref.current = handler;

  useEffect(() => {
    if (!frameHandlers.has(type)) frameHandlers.set(type, new Set());
    const fn = (f: InboundFrame) => ref.current(f as Extract<InboundFrame, { type: T }>);
    frameHandlers.get(type)!.add(fn);
    if (!ws && !retryTimeout) connect();
    return () => {
      frameHandlers.get(type)?.delete(fn);
    };
  }, [type]);
}

export function startWs() {
  if (!ws && !retryTimeout) connect();
}
