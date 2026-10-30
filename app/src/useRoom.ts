import { useCallback, useEffect, useRef, useState } from "react";
import { View, wsUrl } from "./api";

export type ConnectionStatus = "connecting" | "open" | "reconnecting";

/** Live room view over a WebSocket, reconnecting with backoff (wifi drops cost nothing). */
export function useRoom(roomId: string, token: string | null) {
  const [view, setView] = useState<View | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let stopped = false;
    let attempt = 0;
    let timer: number | undefined;

    const connect = () => {
      const query = token ? `?token=${encodeURIComponent(token)}` : "";
      const ws = new WebSocket(
        wsUrl(`/rooms/${encodeURIComponent(roomId)}/ws${query}`),
      );
      wsRef.current = ws;
      ws.onopen = () => {
        attempt = 0;
        setStatus("open");
      };
      ws.onmessage = (msg) => {
        const data = JSON.parse(msg.data as string);
        if (data.kind === "view") setView(data as View);
        else if (data.kind === "error") setError(String(data.detail));
      };
      ws.onclose = () => {
        if (stopped) return;
        setStatus("reconnecting");
        timer = window.setTimeout(
          connect,
          Math.min(500 * 2 ** attempt++, 8000),
        );
      };
    };

    setStatus("connecting");
    connect();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      wsRef.current?.close();
    };
  }, [roomId, token]);

  const sendRaw = useCallback((message: object) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN)
      ws.send(JSON.stringify(message));
    else setError("Not connected — reconnecting…");
  }, []);

  const send = useCallback(
    (type: string, payload: Record<string, unknown> = {}) =>
      sendRaw({ op: "event", type, payload }),
    [sendRaw],
  );
  const undo = useCallback(() => sendRaw({ op: "undo" }), [sendRaw]);
  const clearError = useCallback(() => setError(null), []);

  return { view, status, error, clearError, send, undo };
}

export type RoomActions = Pick<ReturnType<typeof useRoom>, "send" | "undo">;
