import { useEffect, useRef, useState } from "react";
import { storageGet, storageSet } from "./api";
import {
  Command,
  VoiceContext,
  listen,
  parseCommand,
  speechSupported,
} from "./voice";

const VOICE_KEY = "calabria.voice";

export const VOICE_HELP: [string, string][] = [
  ["end turn · pass", "pass the turn"],
  ["untap", "untap your permanents"],
  ["lose 3 · gain 2", "your life"],
  ["hit Bea for 4 · opponent loses 2", "their life"],
  ["play Lightning Bolt", "put a card into play"],
  ["one · two · three", "pick a scan candidate"],
  ["roll a d20 · flip a coin", "dice"],
  ["combat · main · end step", "phase"],
  ["scan · undo", ""],
];

/** Mic toggle: always-on listening for short command phrases. */
export function VoiceControl({
  ctx,
  onCommand,
}: {
  ctx: VoiceContext;
  onCommand: (c: Command, heard: string) => void;
}) {
  const supported = speechSupported();
  const [on, setOn] = useState(
    () => supported && storageGet(VOICE_KEY) === "on",
  );
  const [heard, setHeard] = useState<{ text: string; ok: boolean } | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [help, setHelp] = useState(false);

  const ctxRef = useRef(ctx);
  ctxRef.current = ctx;
  const onCommandRef = useRef(onCommand);
  onCommandRef.current = onCommand;

  useEffect(() => {
    storageSet(VOICE_KEY, on ? "on" : "off");
    if (!on) return;
    setError(null);
    return listen(
      (text) => {
        const cmd = parseCommand(text, ctxRef.current);
        setHeard({ text, ok: cmd !== null });
        if (cmd) onCommandRef.current(cmd, text);
      },
      (message) => {
        setError(message);
        setOn(false);
      },
    );
  }, [on]);

  useEffect(() => {
    if (!heard) return;
    const t = window.setTimeout(() => setHeard(null), 4000);
    return () => window.clearTimeout(t);
  }, [heard]);

  if (!supported) {
    return (
      <span
        className="voice muted"
        title="Voice commands need Chrome, Edge or Safari"
      >
        🎙 n/a
      </span>
    );
  }

  return (
    <span className="voice">
      <button
        className={`mic ${on ? "live" : ""}`}
        onClick={() => setOn((v) => !v)}
        title={
          on ? "Voice commands on — click to stop" : "Turn on voice commands"
        }
      >
        🎙 {on ? "Listening" : "Voice"}
      </button>
      <button
        className="ghost help-btn"
        onClick={() => setHelp((h) => !h)}
        title="What can I say?"
      >
        ?
      </button>
      {heard && (
        <span className={`heard ${heard.ok ? "ok" : ""}`}>“{heard.text}”</span>
      )}
      {error && <span className="error small">{error}</span>}
      {help && (
        <div className="voice-help" onClick={() => setHelp(false)}>
          <strong>Say…</strong>
          <dl>
            {VOICE_HELP.map(([say, what]) => (
              <div key={say}>
                <dt>{say}</dt>
                <dd>{what}</dd>
              </div>
            ))}
          </dl>
          <p className="muted small">
            Only short command phrases count; normal table talk is ignored.
          </p>
        </div>
      )}
    </span>
  );
}
