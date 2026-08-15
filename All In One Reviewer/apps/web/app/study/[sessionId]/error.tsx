"use client";

import Link from "next/link";

export default function StudyError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <main className="route-error"><p className="eyebrow">Study route unavailable</p><h1>Your session could not render.</h1><p>Unsent answer text stays in this browser and is not submitted by this boundary.</p><button type="button" onClick={reset}>Retry session</button><Link href="/">Return to workspace</Link></main>;
}
