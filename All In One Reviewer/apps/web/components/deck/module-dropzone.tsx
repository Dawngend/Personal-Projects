"use client";

import { DragEvent, useRef, useState } from "react";

type Props = { disabled?: boolean; onFiles: (files: File[]) => void };

export function ModuleDropzone({ disabled, onFiles }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const accept = (files: FileList | File[]) => onFiles(Array.from(files).filter((file) => /\.(pdf|pptx)$/i.test(file.name)));
  const drop = (event: DragEvent<HTMLDivElement>) => { event.preventDefault(); setDragging(false); accept(event.dataTransfer.files); };
  return <div className={`dropzone ${dragging ? "dropzone-active" : ""}`} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={drop}>
    <input ref={input} type="file" accept=".pdf,.pptx,application/pdf,application/vnd.openxmlformats-officedocument.presentationml.presentation" multiple hidden onChange={(event) => event.target.files && accept(event.target.files)} />
    <span aria-hidden="true">＋</span><strong>Drop course material here</strong><p>PDF or PPTX · up to 20 MB per module</p>
    <button type="button" onClick={() => input.current?.click()} disabled={disabled}>Choose files</button>
  </div>;
}
