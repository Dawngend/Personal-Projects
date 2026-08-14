"use client";

import type { ModuleItem } from "@/lib/api";

type Props = { modules: ModuleItem[]; selected: string[]; onChange: (ids: string[]) => void };

export function ModuleShelf({ modules, selected, onChange }: Props) {
  if (!modules.length) return <p className="quiet">Your uploaded modules will appear here. Select one or more to build a deck.</p>;
  return <ul className="module-shelf" aria-label="Uploaded modules">{modules.map((module) => {
    const checked = selected.includes(module.id);
    return <li key={module.id}><label><input type="checkbox" checked={checked} onChange={() => onChange(checked ? selected.filter((id) => id !== module.id) : [...selected, module.id])} /><span className="module-mark" aria-hidden="true">{checked ? "●" : "○"}</span><span><strong>{module.filename}</strong><small>{module.extractionStatus === "pending" ? "Ready for generation" : module.extractionStatus}</small></span><code>{Math.ceil(module.sizeBytes / 1024)} KB</code></label></li>;
  })}</ul>;
}
