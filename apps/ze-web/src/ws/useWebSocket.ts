import { useEffect, useRef } from "react";
import { create } from "zustand";
import { type InboundFrame, type OutboundFrame } from "./protocol";
import { getConfig } from "@/config/AppConfig";

// ── Store ─────────────────────────────────────────────────────────────────────

interface WsStore {
  isConnected: boolean;
  isThinking: boolean;
  lastFrame: InboundFrame | null;
  setConnected: (v: boolean) => void;
  setThinking: (v: boolean) => void;
  pushFrame: (f: InboundFrame) => void;
}

export const useWsStore = create<WsStore>((set) => ({
  isConnected: false,
  isThinking: false,
  lastFrame: null,
  setConnected: (v) => set({ isConnected: v }),
  setThinking: (v) => set({ isThinking: v }),
  pushFrame: (f) => set({ lastFrame: f }),
}));

// ── Singleton WS manager (lives outside React) ────────────────────────────────

let ws: WebSocket | null = null;
let retryTimeout: ReturnType<typeof setTimeout> | null = null;
let retryDelay = 1000;
let pingInterval: ReturnType<typeof setInterval> | null = null;
let frameListeners: Array<(f: InboundFrame) => void> = [];

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
    useWsStore.getState().pushFrame(frame);
    frameListeners.forEach((l) => l(frame));
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

export function send(frame: OutboundFrame) {
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(frame));
  }
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

export function useWebSocket(onFrame: (f: InboundFrame) => void) {
  const onFrameRef = useRef(onFrame);
  onFrameRef.current = onFrame;

  useEffect(() => {
    const listener = (f: InboundFrame) => onFrameRef.current(f);
    frameListeners.push(listener);

    if (!ws && !retryTimeout) connect();

    return () => {
      frameListeners = frameListeners.filter((l) => l !== listener);
    };
  }, []);
}

export function startWs() {
  if (!ws && !retryTimeout) connect();
}
