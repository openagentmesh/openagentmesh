import { FormEvent, useEffect, useRef, useState } from "react";
import { DecodedEvent, subscribeSubjects } from "../lib/events";

const MAX_BUFFER = 200;
const DEFAULT_PATTERN = "mesh.>";

/**
 * Live event feed for any NATS subject pattern reachable from the browser.
 * Operator edits the pattern at runtime; submitting unsubscribes the old
 * pattern before opening the new one. Buffer capped at MAX_BUFFER events to
 * bound rendering cost (T-02-08-03).
 */
export function EventFeed() {
  const [pattern, setPattern] = useState<string>(DEFAULT_PATTERN);
  const [activePattern, setActivePattern] = useState<string>(DEFAULT_PATTERN);
  const [events, setEvents] = useState<DecodedEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  const stopRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setEvents([]);
    subscribeSubjects(activePattern, (e) => {
      if (cancelled) return;
      setEvents((prev) => {
        const next = [e, ...prev];
        if (next.length > MAX_BUFFER) next.length = MAX_BUFFER;
        return next;
      });
    })
      .then((stop) => {
        if (cancelled) {
          stop();
          return;
        }
        stopRef.current = stop;
      })
      .catch((err) => setError(String(err)));

    return () => {
      cancelled = true;
      if (stopRef.current) {
        stopRef.current();
        stopRef.current = null;
      }
    };
  }, [activePattern]);

  function applyPattern(e: FormEvent) {
    e.preventDefault();
    setActivePattern(pattern);
  }

  function renderPayload(payload: unknown, raw: string): string {
    if (typeof payload === "string") return payload;
    try {
      return JSON.stringify(payload);
    } catch {
      return raw;
    }
  }

  // Subject color accents: severity-adjacent subjects pick up the ember ramp;
  // everything else stays neutral so the ramp keeps its meaning.
  function subjectTone(subject: string): string {
    if (subject.startsWith("mesh.briefing.")) return "text-ember-400";
    if (subject.startsWith("mesh.survey.")) return "text-ember-300";
    if (subject.startsWith("mesh.chaos.")) return "text-dead";
    if (subject.startsWith("mesh.swarm.")) return "text-ink-300";
    return "text-ink-200";
  }

  return (
    <section className="flex h-full min-h-0 flex-col">
      <header className="flex items-center gap-2 border-b border-ink-700 px-3 py-2">
        <h2 className="microlabel mr-1 whitespace-nowrap">Event feed</h2>
        <form onSubmit={applyPattern} className="flex flex-1 gap-1.5">
          <input
            aria-label="subject-pattern"
            className="min-w-0 flex-1 rounded border border-ink-700 bg-ink-950 px-2 py-1 font-mono text-xs text-ink-100 focus:border-ember-500 focus:outline-none"
            value={pattern}
            onChange={(ev) => setPattern(ev.target.value)}
            placeholder="mesh.>"
            spellCheck={false}
          />
          <button
            type="submit"
            className="rounded border border-ink-600 bg-ink-800 px-2.5 py-1 text-xs text-ink-100 transition-colors hover:border-ember-500 hover:text-ember-300"
          >
            Subscribe
          </button>
        </form>
        <span className="whitespace-nowrap font-mono text-[10px] tabular-nums text-ink-500">
          {events.length}/{MAX_BUFFER}
        </span>
      </header>
      {error && (
        <div className="border-b border-dead/30 bg-dead/10 px-3 py-2 text-xs text-dead">
          {error}
        </div>
      )}
      {events.length === 0 && !error ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-1 text-center">
          <p className="text-sm text-ink-300">Listening on <span className="font-mono text-ink-200">{activePattern}</span></p>
          <p className="text-[11px] text-ink-500">No messages yet. Spawn a fire in the scenario UI to light this up.</p>
        </div>
      ) : (
        <ul className="min-h-0 flex-1 overflow-auto font-mono text-xs">
          {events.map((ev, i) => (
            <li
              key={`${ev.receivedAt}-${i}`}
              className={`border-b border-ink-800 px-3 py-1.5 ${i === 0 ? "animate-feed-in" : ""}`}
            >
              <div className="flex justify-between gap-2">
                <span className={`truncate ${subjectTone(ev.subject)}`}>{ev.subject}</span>
                <span className="whitespace-nowrap tabular-nums text-ink-500">
                  {new Date(ev.receivedAt).toLocaleTimeString("en-GB")}
                </span>
              </div>
              <pre className="mt-0.5 max-h-16 overflow-hidden whitespace-pre-wrap break-all text-[11px] leading-snug text-ink-400">
                {renderPayload(ev.payload, ev.raw)}
              </pre>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
