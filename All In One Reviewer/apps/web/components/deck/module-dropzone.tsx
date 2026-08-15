"use client";

import { DragEvent, useRef, useState } from "react";

/** Mirrors `max_upload_bytes` in andyhub_api/settings.py. The API returns 413
 *  `upload_too_large` past this; rejecting here avoids sending the bytes first. */
const MAX_BYTES = 20 * 1024 * 1024;

type Props = { disabled?: boolean; onFiles: (files: File[]) => void };

type Rejection = { name: string; reason: "type" | "size" };

export function ModuleDropzone({ disabled, onFiles }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [rejected, setRejected] = useState<Rejection[]>([]);
  const accept = (files: FileList | File[]) => {
    const rejections: Rejection[] = [];
    const accepted = Array.from(files).filter((file) => {
      if (!/\.(pdf|pptx)$/i.test(file.name)) {
        rejections.push({ name: file.name, reason: "type" });
        return false;
      }
      if (file.size > MAX_BYTES) {
        rejections.push({ name: file.name, reason: "size" });
        return false;
      }
      return true;
    });
    setRejected(rejections);
    if (accepted.length) onFiles(accepted);
  };
  const drop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    accept(event.dataTransfer.files);
  };
  return (
    <div
      className={`dropzone ${dragging ? "dropzone-active" : ""}`}
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={drop}
    >
      <input
        ref={input}
        type="file"
        accept=".pdf,.pptx,application/pdf,application/vnd.openxmlformats-officedocument.presentationml.presentation"
        multiple
        hidden
        onChange={(event) => event.target.files && accept(event.target.files)}
      />
      <span aria-hidden="true">＋</span>
      <strong>Drop course material here</strong>
      <p>PDF or PPTX · up to 20 MB per module</p>
      <button type="button" onClick={() => input.current?.click()} disabled={disabled}>
        Choose files
      </button>
      {rejected.length > 0 && (
        <ul className="dropzone-rejects" aria-live="polite">
          {rejected.map((file) => (
            <li key={`${file.reason}-${file.name}`}>
              {file.name} — {file.reason === "size" ? "over 20 MB" : "not a PDF or PPTX"}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
