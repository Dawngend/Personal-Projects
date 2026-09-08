"use client";

import { useEffect, useRef, useState } from "react";
import styles from "./reviewer-view.module.css";

export function PdfViewer({ url }: { url: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [pageCount, setPageCount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const documentRef = useRef<import("pdfjs-dist").PDFDocumentProxy | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    (async () => {
      const pdfjsLib = await import("pdfjs-dist");
      pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
        "pdfjs-dist/build/pdf.worker.min.mjs",
        import.meta.url,
      ).toString();
      try {
        const document_ = await pdfjsLib.getDocument(url).promise;
        if (cancelled) return;
        documentRef.current = document_;
        setPageCount(document_.numPages);
        setPageNumber(1);
      } catch {
        if (!cancelled) setError("This PDF could not be rendered.");
      }
    })();
    return () => {
      cancelled = true;
      documentRef.current?.destroy();
    };
  }, [url]);

  useEffect(() => {
    const document_ = documentRef.current;
    const canvas = canvasRef.current;
    if (!document_ || !canvas) return;
    let cancelled = false;
    (async () => {
      const page = await document_.getPage(pageNumber);
      if (cancelled) return;
      const viewport = page.getViewport({ scale: 1.35 });
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      const context = canvas.getContext("2d");
      if (!context) return;
      await page.render({ canvasContext: context, viewport }).promise;
    })();
    return () => {
      cancelled = true;
    };
  }, [pageNumber, pageCount]);

  if (error) return <p className={styles.pdfError}>{error}</p>;

  return (
    <div className={styles.pdfPane}>
      <div className={styles.pdfCanvasWrap}>
        <canvas ref={canvasRef} />
      </div>
      {pageCount && (
        <div className={styles.pdfControls}>
          <button
            type="button"
            onClick={() => setPageNumber((page) => Math.max(1, page - 1))}
            disabled={pageNumber <= 1}
          >
            ← Prev
          </button>
          <span>
            Page {pageNumber} of {pageCount}
          </span>
          <button
            type="button"
            onClick={() => setPageNumber((page) => Math.min(pageCount, page + 1))}
            disabled={pageNumber >= pageCount}
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}
