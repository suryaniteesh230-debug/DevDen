import { CheckCircle2, FileText, LoaderCircle, UploadCloud } from "lucide-react";
import { useRef, useState } from "react";
import { api, errorMessage } from "@/lib/api";

export default function DocumentUploadCard({ encounterId, onUploaded }) {
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef(null);

  const upload = async () => {
    if (!encounterId || !file) return;
    setLoading(true);
    setError("");
    try {
      const next = await api.uploadDocument(encounterId, file);
      setResult(next);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      onUploaded?.();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setLoading(false);
    }
  };

  const chooseDrop = (event) => {
    event.preventDefault();
    setDragging(false);
    const next = event.dataTransfer.files?.[0];
    if (next) setFile(next);
  };

  return (
    <article className="interactive-card flex flex-col rounded-lg border border-border bg-card p-3.5">
      <div className="flex items-start gap-2">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <FileText size={14} />
        </span>
        <div>
          <p className="text-xs font-semibold">Clinical document OCR</p>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            Local extraction · bytes deleted after processing
          </p>
        </div>
      </div>

      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragEnter={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={() => setDragging(false)}
        onDrop={chooseDrop}
        className={`pressable mt-3 flex min-h-24 flex-col items-center justify-center rounded-lg border border-dashed px-3 py-4 text-center transition ${dragging ? "scale-[1.01] border-primary bg-primary/10" : file ? "border-primary/40 bg-primary/5" : "border-border bg-surface hover:border-primary/35"}`}
      >
        <UploadCloud size={19} className={dragging ? "text-primary live-dot" : "text-primary"} />
        <span className="mt-2 max-w-full truncate text-[11px] font-medium">
          {file
            ? file.name
            : dragging
              ? "Drop to stage the document"
              : "Drop a report or click to browse"}
        </span>
        <span className="mt-1 text-[9px] text-muted-foreground">
          PNG, JPEG, TIFF, WebP or PDF · 10 MiB · 5 pages
        </span>
      </button>
      <input
        ref={inputRef}
        hidden
        type="file"
        accept="image/png,image/jpeg,image/tiff,image/webp,application/pdf"
        onChange={(event) => setFile(event.target.files?.[0] || null)}
      />

      <button
        type="button"
        onClick={upload}
        disabled={!encounterId || !file || loading}
        className="pressable mt-3 inline-flex items-center justify-center gap-2 rounded-md border border-primary/40 bg-primary/10 px-2.5 py-2 text-[11px] font-medium text-primary hover:bg-primary/15 disabled:opacity-50"
      >
        {loading ? <LoaderCircle size={13} className="animate-spin" /> : <FileText size={13} />}
        {loading ? "OCR and parsing in progress…" : "Extract clinical fields"}
      </button>
      {error ? <p className="view-enter mt-2 text-[11px] text-destructive">{error}</p> : null}
      {result ? (
        <div className="view-enter mt-3 border-t border-border pt-3">
          <div className="flex items-center gap-2">
            <CheckCircle2 size={13} className="text-primary" />
            <p className="text-[10px] font-medium">Extraction persisted with OCR provenance</p>
          </div>
          <p className="mt-2 font-mono text-[9px] text-muted-foreground">
            {result.safe_filename} · {result.ocr_engine_version} · {result.page_count} page(s)
          </p>
          <p className="mt-2 max-h-24 overflow-y-auto whitespace-pre-wrap rounded-md bg-surface p-2 text-[11px] leading-relaxed text-muted-foreground">
            {result.ocr_text || "No text extracted"}
          </p>
          <div className="stagger-grid mt-2 flex flex-wrap gap-1">
            {result.extracted_fields.map((item, index) => (
              <button
                type="button"
                key={`${item.test_name}-${index}`}
                title="Persisted OCR-derived observation"
                className="pressable rounded border border-primary/25 bg-primary/5 px-1.5 py-0.5 text-[10px] text-primary"
              >
                {item.test_name}: {item.value} {item.unit}
              </button>
            ))}
          </div>
          {result.conflicts.length ? (
            <p className="mt-2 rounded-md bg-esi-2/10 px-2 py-1.5 text-[11px] text-esi-2">
              {result.conflicts.length} conflict(s) preserved—manual values remain preferred.
            </p>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
