"use client";

import Link from "next/link";

export default function DeckError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <main className="route-error"><p className="eyebrow">Deck route unavailable</p><h1>This deck could not open.</h1><p>No study response was lost or submitted.</p><button type="button" onClick={reset}>Retry</button><Link href="/">Return to workspace</Link></main>;
}
