import { useEffect, useRef } from "react";
import { create } from "zustand";
import type { WsInboundFrame as InboundFrame, WsOutboundFrame as OutboundFrame } from "@ze/client";
import { getConfig } from "@/config/AppConfig";
import { useSession } from "@/features/chat/hooks/useSession";

// ── Store ─────────────────────────────────────────────────────────────────────

interface WsStore {
  isConnected: boolean;
  isThinking: boolean;
  setConnected: (v: boolean) => void;
  setThinking: (v: boolean) => void;
}

export const useWsStore = create<WsStore>((set) => ({
  isConnected: false,
  isThinking: false,
  setConnected: (v) => set({ isConnected: v }),
  setThinking: (v) => set({ isThinking: v }),
}));

// ── Central frame dispatcher ──────────────────────────────────────────────────

type FrameType = InboundFrame["type"];
const frameHandlers = new Map<FrameType, Set<(f: InboundFrame) => void>>();

function dispatch(frame: InboundFrame) {
  frameHandlers.get(frame.type)?.forEach((h) => h(frame));
}

// ── Singleton WS manager (lives outside React) ────────────────────────────────

let ws: WebSocket | null = null;
let retryTimeout: ReturnType<typeof setTimeout> | null = null;
let retryDelay = 1000;
let pingInterval: ReturnType<typeof setInterval> | null = null;

function buildUrl() {
  const cfg = getConfig();
  if (!cfg) return null;
  const base = cfg.serverUrl.replace(/^http/, "ws");
  const threadId = useSession.getState().threadId;
  return `${base}/ws?token=${encodeURIComponent(cfg.apiKey)}&thread_id=${encodeURIComponent(threadId)}`;
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
    useWsStore.getState().setConnected(true);
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

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useFrame<T extends FrameType>(
  type: T,
  handler: (f: Extract<InboundFrame, { type: T }>) => void,
) {
  const ref = useRef(handler);
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

// Reconnect when the active thread changes so the WS URL picks up the new thread_id.
let activeThreadId = useSession.getState().threadId;
useSession.subscribe((state) => {
  if (state.threadId === activeThreadId) return;
  activeThreadId = state.threadId;
  reconnect();
});
