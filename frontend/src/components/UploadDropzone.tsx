import { useCallback, useState, type DragEvent } from "react";
import { FileUp, Upload } from "lucide-react";

interface UploadDropzoneProps {
  onUpload: (files: File[]) => void;
  uploading?: boolean;
  accept?: string;
  multiple?: boolean;
}

export default function UploadDropzone({
  onUpload,
  uploading = false,
  accept = ".pdf,application/pdf",
  multiple = true,
}: UploadDropzoneProps) {
  const [dragOver, setDragOver] = useState(false);

  const handleFiles = useCallback(
    (fileList: FileList | null) => {
      if (!fileList?.length) return;
      const pdfs = Array.from(fileList).filter(
        (f) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf"),
      );
      if (pdfs.length) onUpload(pdfs);
    },
    [onUpload],
  );

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    handleFiles(e.dataTransfer.files);
  };

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={onDrop}
      className={`relative rounded-xl border-2 border-dashed p-8 text-center transition-colors ${
        dragOver
          ? "border-brand-600 bg-brand-700/5"
          : "border-border bg-surface-muted/30 hover:border-brand-600/50"
      } ${uploading ? "pointer-events-none opacity-60" : ""}`}
    >
      <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-brand-700/10 text-brand-700">
        {uploading ? (
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-brand-700 border-t-transparent" />
        ) : (
          <Upload className="h-6 w-6" />
        )}
      </div>
      <p className="text-sm font-medium text-ink">
        {uploading ? "Uploading documents…" : "Drag & drop PDF files here"}
      </p>
      <p className="mt-1 text-xs text-ink-muted">or click to browse · multiple files supported</p>
      <label className="btn-primary mt-4 cursor-pointer">
        <FileUp className="h-4 w-4" />
        Select PDFs
        <input
          type="file"
          className="sr-only"
          accept={accept}
          multiple={multiple}
          disabled={uploading}
          onChange={(e) => handleFiles(e.target.files)}
        />
      </label>
    </div>
  );
}
