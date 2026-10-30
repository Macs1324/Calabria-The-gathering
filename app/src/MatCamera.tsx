import { MutableRefObject, useEffect, useRef, useState } from "react";
import {
  CardEntry,
  ScanCandidate,
  ScannedCard,
  api,
  storageGet,
  storageSet,
} from "./api";
import {
  Observation,
  Plan,
  observe,
  reconcile,
  sameObservation,
} from "./matWatch";
import { Icon } from "./Icon";
import { overlayOpen } from "./Menu";

const MAX_WIDTH = 1280; // frames are downscaled before upload; plenty for 256-bit hashes
const TICK_MS = 300; // motion check cadence
const THUMB_W = 64;
const THUMB_H = 36;
const MOVING = 0.02; // mean |Δ| between ticks (0..1) above which the scene is in motion
const CHANGED = 0.012; // mean |Δ| vs the last scanned view that's worth a new scan
const CONFIRM_DELAY_MS = 450; // second look before acting on a change
const WATCH_KEY = "calabria.watch";

export type WatchStatus =
  "off" | "starting" | "watching" | "moving" | "scanning" | "error";

/**
 * The player's own webcam over their own mat.
 *
 * Watch mode (default): a cheap thumbnail diff gates scans — the server is
 * only asked once the scene changed and then held still, and every change is
 * looked at twice before anything happens (hands passing over cards produce
 * no actions). The resulting plan is handed to `onPlan`.
 * Manual mode: Scan button / Space / "scan" → candidates for the largest card.
 */
export function MatCamera({
  mine,
  onPlan,
  onCandidates,
  scanRef,
  onClose,
}: {
  mine: CardEntry[];
  onPlan: (plan: Plan) => void;
  onCandidates: (c: ScanCandidate[]) => void;
  scanRef: MutableRefObject<(() => void) | null>;
  onClose: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [deviceId, setDeviceId] = useState<string>(
    () => storageGet("calabria.camera") ?? "",
  );
  const [watch, setWatch] = useState(() => storageGet(WATCH_KEY) !== "off");
  const [status, setStatus] = useState<WatchStatus>("starting");
  const [problem, setProblem] = useState<string | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);
  const [seen, setSeen] = useState<ScannedCard[]>([]);
  const [frameSize, setFrameSize] = useState<[number, number]>([1280, 720]);

  // Latest props for the polling loop, without restarting it on every render.
  const mineRef = useRef(mine);
  mineRef.current = mine;
  const onPlanRef = useRef(onPlan);
  onPlanRef.current = onPlan;

  useEffect(() => {
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      setProblem(
        "Browsers only allow the camera on https:// pages or localhost.",
      );
      setStatus("error");
      return;
    }
    let stream: MediaStream | null = null;
    let live = true;
    setStatus("starting");
    navigator.mediaDevices
      .getUserMedia({
        video: deviceId
          ? { deviceId: { exact: deviceId } }
          : { width: { ideal: 1920 }, height: { ideal: 1080 } },
        audio: false,
      })
      .then(async (s) => {
        if (!live) return s.getTracks().forEach((t) => t.stop());
        stream = s;
        setProblem(null);
        setStatus("watching");
        if (videoRef.current) videoRef.current.srcObject = s;
        const all = await navigator.mediaDevices.enumerateDevices();
        if (live) setDevices(all.filter((d) => d.kind === "videoinput"));
      })
      .catch((e: unknown) => {
        setProblem(
          `Camera unavailable: ${e instanceof Error ? e.message : String(e)}`,
        );
        setStatus("error");
      });
    return () => {
      live = false;
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [deviceId]);

  const grab = (): { b64: string; w: number; h: number } | null => {
    const video = videoRef.current;
    if (!video || !video.videoWidth) return null;
    const scale = Math.min(1, MAX_WIDTH / video.videoWidth);
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    canvas
      .getContext("2d")
      ?.drawImage(video, 0, 0, canvas.width, canvas.height);
    return {
      b64: canvas.toDataURL("image/jpeg", 0.85).split(",")[1],
      w: canvas.width,
      h: canvas.height,
    };
  };

  // --- manual scan --------------------------------------------------------
  const busyRef = useRef(false);
  const manualScan = async () => {
    const frame = grab();
    if (!frame || busyRef.current) return;
    busyRef.current = true;
    setScanError(null);
    try {
      const { cards } = await api.scan(frame.b64, "single");
      setFrameSize([frame.w, frame.h]);
      setSeen(cards);
      onCandidates(cards[0]?.candidates ?? []);
    } catch (e) {
      setScanError(
        `Scan failed: ${e instanceof Error ? e.message : String(e)}`,
      );
    } finally {
      busyRef.current = false;
    }
  };
  const manualRef = useRef(manualScan);
  manualRef.current = manualScan;
  useEffect(() => {
    scanRef.current = () => manualRef.current();
    return () => {
      scanRef.current = null;
    };
  }, [scanRef]);

  // --- watch loop -----------------------------------------------------------
  useEffect(() => {
    storageSet(WATCH_KEY, watch ? "on" : "off");
    if (!watch) return;
    const thumbCanvas = document.createElement("canvas");
    thumbCanvas.width = THUMB_W;
    thumbCanvas.height = THUMB_H;
    const ctx = thumbCanvas.getContext("2d", { willReadFrequently: true });
    let prevThumb: Uint8ClampedArray | null = null;
    let scannedThumb: Uint8ClampedArray | null = null;
    let committed: Observation | null = null;
    let pending: Observation | null = null;
    let confirmTimer: number | undefined;
    let backoffUntil = 0; // after a failed scan, pause instead of retrying every tick
    let stopped = false;
    const confirmLater = (ms: number) => {
      window.clearTimeout(confirmTimer);
      confirmTimer = window.setTimeout(look, ms);
    };

    const thumb = (): Uint8ClampedArray | null => {
      const video = videoRef.current;
      if (!ctx || !video || !video.videoWidth) return null;
      ctx.drawImage(video, 0, 0, THUMB_W, THUMB_H);
      const rgba = ctx.getImageData(0, 0, THUMB_W, THUMB_H).data;
      const gray = new Uint8ClampedArray(THUMB_W * THUMB_H);
      for (let i = 0; i < gray.length; i++)
        gray[i] = (rgba[i * 4] + rgba[i * 4 + 1] + rgba[i * 4 + 2]) / 3;
      return gray;
    };
    const diff = (a: Uint8ClampedArray, b: Uint8ClampedArray) => {
      let sum = 0;
      for (let i = 0; i < a.length; i++) sum += Math.abs(a[i] - b[i]);
      return sum / a.length / 255;
    };

    const look = async () => {
      if (stopped) return;
      if (busyRef.current) {
        if (pending) confirmLater(TICK_MS); // a manual scan is running: keep the second look
        return;
      }
      const frame = grab();
      const t = thumb();
      if (!frame || !t) return;
      busyRef.current = true;
      setStatus("scanning");
      try {
        const { cards } = await api.scan(frame.b64, "all");
        if (stopped) return;
        scannedThumb = t;
        setFrameSize([frame.w, frame.h]);
        setSeen(cards);
        setScanError(null);
        const obs = observe(cards);
        if (committed && sameObservation(obs, committed)) {
          pending = null; // nothing changed after all
        } else if (pending && sameObservation(obs, pending)) {
          onPlanRef.current(reconcile(committed, obs, mineRef.current, cards));
          committed = obs;
          pending = null;
        } else {
          pending = obs; // first sighting of a change: look again before acting
          confirmLater(CONFIRM_DELAY_MS);
        }
      } catch (e) {
        setScanError(`Scan failed: ${e instanceof Error ? e.message : String(e)}`);
        backoffUntil = Date.now() + 3000;
        if (pending) confirmLater(3000);
      } finally {
        busyRef.current = false;
        if (!stopped) setStatus("watching");
      }
    };

    const timer = window.setInterval(() => {
      if (Date.now() < backoffUntil) return;
      const t = thumb();
      if (!t) return;
      const moving = prevThumb !== null && diff(t, prevThumb) > MOVING;
      prevThumb = t;
      if (moving) {
        setStatus("moving");
        return;
      }
      if (!scannedThumb || diff(t, scannedThumb) > CHANGED) look();
      else setStatus((s) => (s === "moving" ? "watching" : s));
    }, TICK_MS);

    return () => {
      stopped = true;
      window.clearInterval(timer);
      window.clearTimeout(confirmTimer);
      setStatus("watching");
    };
    // A new camera means a new view: start from a fresh baseline.
  }, [watch, deviceId]);

  // Space scans manually, unless you're typing. A focused button would
  // otherwise "click" on Space, so take the key from it.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (e.code !== "Space" || target.closest("input, textarea, select"))
        return;
      // Toggles and chips are answered by Space natively; leave them be.
      if (target.closest(".segmented, .chip, [role=switch]") || overlayOpen())
        return;
      e.preventDefault();
      if (target instanceof HTMLButtonElement) target.blur();
      manualRef.current();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const label: Record<WatchStatus, string> = {
    off: "Camera off",
    starting: "Starting camera…",
    watching: watch
      ? `Watching · ${seen.length} card${seen.length === 1 ? "" : "s"}`
      : "Ready",
    moving: "Hold still…",
    scanning: "Looking…",
    error: "Camera unavailable",
  };

  return (
    <section className="dock-section mat-camera">
      <div className="cam-frame">
        <video ref={videoRef} autoPlay playsInline muted />
        <svg
          className="overlay"
          viewBox={`0 0 ${frameSize[0]} ${frameSize[1]}`}
          preserveAspectRatio="xMidYMid meet"
        >
          {seen.map((c, i) => (
            <polygon
              key={i}
              className={c.confident ? "sure" : "unsure"}
              points={c.quad.map((p) => p.join(",")).join(" ")}
            />
          ))}
        </svg>
        <span className={`cam-status ${status}`}>
          <span className="dot" />
          {label[status]}
        </span>
        <button
          className="icon-btn cam-close"
          aria-label="Turn the camera off"
          data-tip="Camera off"
          onClick={onClose}
        >
          <Icon name="x" size={16} />
        </button>
        {(problem || scanError) && (
          <p className="cam-error">{problem ?? scanError}</p>
        )}
      </div>
      <div className="cam-controls">
        <label
          className="switch"
          title="Play, tap and untap cards by moving them on your mat"
        >
          <input
            type="checkbox"
            role="switch"
            checked={watch}
            onChange={(e) => setWatch(e.currentTarget.checked)}
          />
          <span className="track" />
          Auto-play
        </label>
        {devices.length > 1 && (
          <select
            aria-label="Camera"
            value={deviceId}
            onChange={(e) => {
              setDeviceId(e.currentTarget.value);
              storageSet("calabria.camera", e.currentTarget.value || null);
            }}
          >
            <option value="">Default camera</option>
            {devices.map((d, i) => (
              <option key={d.deviceId} value={d.deviceId}>
                {d.label || `Camera ${i + 1}`}
              </option>
            ))}
          </select>
        )}
        <button
          onClick={manualScan}
          disabled={!!problem}
          title="Scan the card you hold up (Space)"
        >
          <Icon name="scan" size={16} />
          Scan <kbd>Space</kbd>
        </button>
      </div>
      <p className="hint">
        {watch
          ? "Lay cards down, tap or untap them, take them away — the table follows. Unsure cards ask first."
          : "Hold one card flat under the camera and press Space."}
      </p>
    </section>
  );
}
