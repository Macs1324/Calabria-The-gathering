// Voice commands for hands-free play.
//
// Matching is anchored to the *whole* utterance, so ordinary table talk
// ("I think I should pass on that") never fires a command; only short,
// command-shaped phrases do. Recognition itself uses the browser's Web Speech
// API (Chrome/Edge/Safari; Chrome sends audio to Google for transcription).

export type Command =
  | { kind: "event"; type: string; payload: Record<string, unknown> }
  | { kind: "undo" }
  | { kind: "scan" }
  | { kind: "play"; query: string }
  | { kind: "pick"; index: number };

export interface VoiceContext {
  you: string;
  players: string[];
}

const NUMBERS: Record<string, number> = {
  one: 1,
  two: 2,
  three: 3,
  four: 4,
  five: 5,
  six: 6,
  seven: 7,
  eight: 8,
  nine: 9,
  ten: 10,
  eleven: 11,
  twelve: 12,
  thirteen: 13,
  fourteen: 14,
  fifteen: 15,
  sixteen: 16,
  seventeen: 17,
  eighteen: 18,
  nineteen: 19,
  twenty: 20,
  a: 1,
  an: 1,
};
const ORDINALS: Record<string, number> = {
  one: 0,
  first: 0,
  "1": 0,
  two: 1,
  second: 1,
  "2": 1,
  three: 2,
  third: 2,
  "3": 2,
};
const NUM = "(\\d+|[a-z]+)";

function toNumber(word: string): number | null {
  if (/^\d+$/.test(word)) return Number(word);
  return NUMBERS[word] ?? null;
}

function normalize(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "") // "José" and "jose" are the same name
    .toLowerCase()
    .replace(/[.,!?]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^(ok(ay)?|hey)?\s*calabria\s*/, ""); // optional wake word
}

const event = (
  type: string,
  payload: Record<string, unknown> = {},
): Command => ({ kind: "event", type, payload });
const life = (delta: number, player: string): Command =>
  event("life_change", { delta, player });

export function parseCommand(raw: string, ctx: VoiceContext): Command | null {
  const t = normalize(raw);
  if (!t) return null;

  const others = ctx.players.filter((p) => p !== ctx.you);
  const target = (who: string): string | null => {
    if (/^(the )?(opponent|them|him|her)$/.test(who))
      return others.length === 1 ? others[0] : null;
    return ctx.players.find((p) => normalize(p) === who) ?? null;
  };

  if (/^(end|pass)( the| my)? turn$|^(i )?pass$|^next turn$/.test(t))
    return event("turn_end");
  if (/^untap( all| everything)?$/.test(t)) return event("untap_all");
  if (/^undo( that)?$/.test(t)) return { kind: "undo" };
  if (/^scan( (it|this|card))?$/.test(t)) return { kind: "scan" };

  const phase = t.match(
    /^(go to |move to )?(combat|main|second main|main two|end step|end)( phase)?$/,
  );
  if (phase) {
    const name = {
      combat: "combat",
      main: "main",
      "second main": "main 2",
      "main two": "main 2",
      "end step": "end",
      end: "end",
    }[phase[2]];
    return name ? event("phase_set", { phase: name }) : null;
  }

  const roll = t.match(/^roll( a)?( d ?(\d+)| dice| die)$/);
  if (roll) return event("dice_roll", { sides: roll[3] ? Number(roll[3]) : 6 });
  if (/^(flip|toss)( a)? coin$/.test(t))
    return event("dice_roll", { sides: 2 });

  let m = t.match(new RegExp(`^(i )?(lose|minus) ${NUM}( life)?$`));
  if (m) return withNumber(m[3], (n) => life(-n, ctx.you));
  m = t.match(new RegExp(`^(i )?(gain|plus) ${NUM}( life)?$`));
  if (m) return withNumber(m[3], (n) => life(n, ctx.you));

  m = t.match(new RegExp(`^hit ([a-z0-9 ]+?) for ${NUM}( damage)?$`));
  if (m) return withTarget(target(m[1]), m[2], -1);
  m = t.match(new RegExp(`^deal ${NUM}( damage)? to ([a-z0-9 ]+)$`));
  if (m) return withTarget(target(m[3]), m[1], -1);
  m = t.match(
    new RegExp(`^([a-z0-9 ]+?) (loses|takes|minus) ${NUM}( life| damage)?$`),
  );
  if (m) return withTarget(target(m[1]), m[3], -1);
  m = t.match(new RegExp(`^([a-z0-9 ]+?) (gains|plus) ${NUM}( life)?$`));
  if (m) return withTarget(target(m[1]), m[3], 1);

  m = t.match(/^(play|cast) (.+)$/);
  if (m) return { kind: "play", query: m[2] };

  m = t.match(
    /^(the )?(number )?(first|second|third|one|two|three|1|2|3)( one)?$/,
  );
  if (m) return { kind: "pick", index: ORDINALS[m[3]] };

  return null;
}

function withNumber(
  word: string,
  make: (n: number) => Command,
): Command | null {
  const n = toNumber(word);
  return n !== null && n > 0 && n < 1000 ? make(n) : null;
}

function withTarget(
  player: string | null,
  word: string,
  sign: 1 | -1,
): Command | null {
  if (!player) return null;
  return withNumber(word, (n) => life(sign * n, player));
}

// --- browser speech recognition --------------------------------------------

interface RecognitionLike {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult:
    | ((e: {
        resultIndex: number;
        results: ArrayLike<
          ArrayLike<{ transcript: string }> & { isFinal: boolean }
        >;
      }) => void)
    | null;
  onend: (() => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  start(): void;
  stop(): void;
}

type RecognitionCtor = new () => RecognitionLike;

export function speechSupported(): boolean {
  const w = window as unknown as {
    SpeechRecognition?: RecognitionCtor;
    webkitSpeechRecognition?: RecognitionCtor;
  };
  return Boolean(w.SpeechRecognition ?? w.webkitSpeechRecognition);
}

/** Listen continuously, reporting each final phrase. Returns a stop function. */
export function listen(
  onPhrase: (text: string) => void,
  onError: (message: string) => void,
): () => void {
  const w = window as unknown as {
    SpeechRecognition?: RecognitionCtor;
    webkitSpeechRecognition?: RecognitionCtor;
  };
  const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
  if (!Ctor) {
    onError("Voice commands need Chrome, Edge or Safari.");
    return () => {};
  }
  let stopped = false;
  const rec = new Ctor();
  rec.continuous = true;
  rec.interimResults = false;
  rec.lang = "en-US";
  rec.onresult = (e) => {
    for (let i = e.resultIndex; i < e.results.length; i++) {
      if (e.results[i].isFinal) onPhrase(e.results[i][0].transcript);
    }
  };
  const reasons: Record<string, string> = {
    "not-allowed": "Microphone access was blocked.",
    "service-not-allowed": "Microphone access was blocked.",
    "audio-capture": "No microphone found.",
    network: "Voice recognition is unreachable (it needs an internet connection).",
  };
  let restart: number | undefined;
  rec.onerror = (e) => {
    // Silence just ends the session (restarted below). Anything else would
    // fail again immediately, so stop instead of spinning.
    if (e.error === "no-speech" || e.error === "aborted") return;
    stopped = true;
    onError(reasons[e.error] ?? `Voice stopped (${e.error}).`);
  };
  rec.onend = () => {
    // Browsers end sessions after silence; keep listening, gently.
    if (!stopped) restart = window.setTimeout(() => !stopped && rec.start(), 250);
  };
  rec.start();
  return () => {
    stopped = true;
    window.clearTimeout(restart);
    rec.stop();
  };
}
