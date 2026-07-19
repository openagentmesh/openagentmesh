/**
 * Badges from the catalog capability flags (ADR-0031 shapes, Watcher retired):
 * `call` for request/reply, `stream` for chunked replies, `events` for
 * publisher/source-only agents reachable via the event feed.
 */
export default function CapabilityBadges({
  invocable,
  streaming,
}: {
  invocable: boolean;
  streaming: boolean;
}) {
  const badges: Array<{ label: string; className: string }> = [];
  if (invocable && !streaming) {
    badges.push({ label: "call", className: "bg-sky-100 text-sky-800" });
  }
  if (streaming) {
    badges.push({ label: "stream", className: "bg-violet-100 text-violet-800" });
  }
  if (!invocable && !streaming) {
    badges.push({ label: "events", className: "bg-slate-200 text-slate-700" });
  }
  return (
    <span className="flex gap-1">
      {badges.map((b) => (
        <span
          key={b.label}
          className={`rounded px-1.5 py-0.5 font-mono text-xs font-medium ${b.className}`}
        >
          {b.label}
        </span>
      ))}
    </span>
  );
}
