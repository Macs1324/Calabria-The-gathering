import { useEffect, useRef, useState } from "react";
import { ScanCandidate, ScannedCard, api } from "./api";

const MAX_WIDTH = 1280; // frames are downscaled before upload; plenty for 256-bit hashes

/** Webcam preview + "Scan" (button or Space). Reports the largest card's candidates. */
export function Camera({
  onCandidates,
}: {
  onCandidates: (c: ScanCandidate[]) => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [deviceId, setDeviceId] = useState<string>("");
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [last, setLast] = useState<ScannedCard | null>(null);
  const [size, setSize] = useState<[number, number]>([1280, 720]);

  useEffect(() => {
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      setProblem(
        "The browser only allows the camera on https:// pages or localhost. Ask the host for the https link (see README → Hosting).",
      );
      return;
    }
    let stream: MediaStream | null = null;
    let live = true;
    navigator.mediaDevices
      .getUserMedia({
        video: deviceId
          ? { deviceId: { exact: deviceId } }
          : { width: { ideal: 1920 }, height: { ideal: 1080 } },
        audio: false,
      })
      .then(async (s) => {
        if (!live) {
          s.getTracks().forEach((t) => t.stop());
          return;
        }
        stream = s;
        setProblem(null);
        if (videoRef.current) videoRef.current.srcObject = s;
        const all = await navigator.mediaDevices.enumerateDevices();
        if (live) setDevices(all.filter((d) => d.kind === "videoinput"));
      })
      .catch((e: unknown) =>
        setProblem(
          `Camera unavailable: ${e instanceof Error ? e.message : String(e)}`,
        ),
      );
    return () => {
      live = false;
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [deviceId]);

  const scan = async () => {
    const video = videoRef.current;
    if (!video || !video.videoWidth || busy) return;
    const scale = Math.min(1, MAX_WIDTH / video.videoWidth);
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    canvas
      .getContext("2d")
      ?.drawImage(video, 0, 0, canvas.width, canvas.height);
    const b64 = canvas.toDataURL("image/jpeg", 0.85).split(",")[1];
    setBusy(true);
    try {
      const { cards } = await api.scan(b64);
      setSize([canvas.width, canvas.height]);
      setLast(cards[0] ?? null);
      onCandidates(cards[0]?.candidates ?? []);
    } catch (e) {
      setProblem(`Scan failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  };

  // Space scans, unless you're typing somewhere.
  const scanRef = useRef(scan);
  scanRef.current = scan;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (
        e.code !== "Space" ||
        (e.target as HTMLElement).closest("input, textarea, select, button")
      )
        return;
      e.preventDefault();
      scanRef.current();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="camera">
      {problem && <p className="error">{problem}</p>}
      <div className="video-wrap">
        <video ref={videoRef} autoPlay playsInline muted />
        {last && (
          <svg
            viewBox={`0 0 ${size[0]} ${size[1]}`}
            preserveAspectRatio="xMidYMid meet"
          >
            <polygon points={last.quad.map((p) => p.join(",")).join(" ")} />
          </svg>
        )}
      </div>
      <div className="row">
        <button className="primary" onClick={scan} disabled={busy || !!problem}>
          {busy ? "Scanning…" : "Scan"} <kbd>Space</kbd>
        </button>
        {devices.length > 1 && (
          <select
            value={deviceId}
            onChange={(e) => setDeviceId(e.currentTarget.value)}
          >
            <option value="">Default camera</option>
            {devices.map((d, i) => (
              <option key={d.deviceId} value={d.deviceId}>
                {d.label || `Camera ${i + 1}`}
              </option>
            ))}
          </select>
        )}
      </div>
      <p className="hint muted">
        Hold one card flat under the camera, fill a good part of the frame, then
        scan.
      </p>
    </div>
  );
}
