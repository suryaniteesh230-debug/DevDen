import { CheckCircle2, LoaderCircle, Mic, Square, UploadCloud, Waves } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, errorMessage } from "@/lib/api";

export default function SpeechInputCard({ encounterId, onUploaded }) {
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState("");
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);
  const inputRef = useRef(null);

  useEffect(() => {
    if (!recording) return undefined;
    const timer = window.setInterval(() => setSeconds((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [recording]);

  const startRecording = async () => {
    setError("");
    setResult(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "";
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => event.data.size && chunksRef.current.push(event.data);
      recorder.onstop = () => {
        const recordedType = mimeType || recorder.mimeType || "audio/webm";
        const extension = extensionForAudioType(recordedType);
        const captured = new File(chunksRef.current, `clinical-speech-${Date.now()}.${extension}`, {
          type: recordedType,
        });
        setFile(captured);
        stream.getTracks().forEach((track) => track.stop());
      };
      recorderRef.current = recorder;
      recorder.start();
      setSeconds(0);
      setRecording(true);
    } catch (caught) {
      setError(errorMessage(caught));
    }
  };

  const stopRecording = () => {
    recorderRef.current?.stop();
    setRecording(false);
  };

  const upload = async () => {
    if (!encounterId || !file) return;
    setLoading(true);
    setError("");
    try {
      const next = await api.uploadSpeech(encounterId, file);
      setResult(next);
      onUploaded?.();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setLoading(false);
    }
  };

  return (
    <article className="interactive-card flex flex-col rounded-lg border border-border bg-card p-3.5">
      <div className="flex items-start gap-2">
        <span
          className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${recording ? "bg-destructive/10 text-destructive live-dot" : "bg-primary/10 text-primary"}`}
        >
          {recording ? <Waves size={14} /> : <Mic size={14} />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-semibold">Speech intake</p>
            {recording ? (
              <span className="font-mono text-[10px] font-medium text-destructive">
                REC {formatTime(seconds)}
              </span>
            ) : null}
          </div>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            Record or upload · transcript kept, audio discarded
          </p>
        </div>
      </div>

      <div
        className={`mt-3 rounded-lg border p-3 transition ${recording ? "border-destructive/35 bg-destructive/5" : "border-border bg-surface"}`}
      >
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={recording ? stopRecording : startRecording}
            disabled={!encounterId || loading}
            className={`pressable inline-flex items-center gap-1.5 rounded-md border px-3 py-2 text-[11px] font-medium disabled:opacity-50 ${recording ? "border-destructive/40 bg-destructive/10 text-destructive" : "border-primary/30 bg-card text-primary"}`}
          >
            {recording ? <Square size={11} /> : <Mic size={11} />}
            {recording ? "Stop and stage" : "Record now"}
          </button>
          <span className="text-[9px] text-muted-foreground">or</span>
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={recording}
            className="pressable inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-2 text-[11px] text-muted-foreground hover:text-foreground disabled:opacity-50"
          >
            <UploadCloud size={11} /> Browse audio
          </button>
        </div>
        <input
          ref={inputRef}
          hidden
          type="file"
          accept=".wav,.mp3,.mpeg,.mpga,.m4a,.mp4,.ogg,.webm,.flac,audio/*"
          onChange={(event) => setFile(event.target.files?.[0] || null)}
        />
        {file ? (
          <p className="view-enter mt-2 truncate rounded-md bg-card px-2 py-1.5 font-mono text-[9px] text-muted-foreground">
            staged: {file.name} · {(file.size / 1024).toFixed(1)} KiB
          </p>
        ) : null}
      </div>

      <button
        type="button"
        onClick={upload}
        disabled={!encounterId || !file || loading || recording}
        className="pressable mt-3 inline-flex items-center justify-center gap-2 rounded-md border border-primary/40 bg-primary/10 px-2.5 py-2 text-[11px] font-medium text-primary hover:bg-primary/15 disabled:opacity-50"
      >
        {loading ? <LoaderCircle size={13} className="animate-spin" /> : <Waves size={13} />}
        {loading ? "Transcribing and extracting…" : "Transcribe and extract symptoms"}
      </button>
      {error ? <p className="view-enter mt-2 text-[11px] text-destructive">{error}</p> : null}
      {result ? (
        <div className="view-enter mt-3 border-t border-border pt-3">
          <div className="flex items-center gap-2">
            <CheckCircle2 size={13} className="text-primary" />
            <p className="text-[10px] font-medium">Transcript persisted with speech provenance</p>
          </div>
          <p className="mt-2 rounded-md bg-surface p-2 text-[11px] leading-relaxed text-muted-foreground">
            “{result.transcript}”
          </p>
          <div className="stagger-grid mt-2 flex flex-wrap gap-1">
            {result.extracted_symptoms.map((item) => (
              <button
                type="button"
                key={item.name}
                title={item.present ? "Present symptom assertion" : "Explicitly negated symptom"}
                className={`pressable rounded border px-1.5 py-0.5 text-[10px] ${item.present ? "border-primary/40 bg-primary/5 text-primary" : "border-border text-muted-foreground line-through"}`}
              >
                {item.present ? "" : "no "}
                {item.name}
              </button>
            ))}
          </div>
          {result.conflicts.length ? (
            <p className="mt-2 rounded-md bg-esi-2/10 px-2 py-1.5 text-[11px] text-esi-2">
              {result.conflicts.length} conflict(s) preserved—manual assertions remain preferred.
            </p>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

function formatTime(seconds) {
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function extensionForAudioType(contentType) {
  const normalized = contentType.split(";", 1)[0].toLowerCase();
  if (normalized === "audio/mp4" || normalized === "audio/x-m4a") return "m4a";
  if (normalized === "audio/ogg") return "ogg";
  if (normalized === "audio/mpeg" || normalized === "audio/mp3") return "mp3";
  if (normalized === "audio/wav" || normalized === "audio/x-wav") return "wav";
  if (normalized === "audio/flac") return "flac";
  return "webm";
}
