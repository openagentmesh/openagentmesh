import { FormEvent, useEffect, useRef, useState } from "react";
import { DecodedEvent, subscribeSubjects } from "../lib/events";

const MAX_BUFFER = 200;
const DEFAULT_PATTERN = "mesh.action.>";

/**
 * Live event feed for any NATS subject pattern reachable from the browser.
 * Default pattern `mesh.action.>` shows heli/ffunit/medevac status pubsub
 * (Phase 2). Operator can edit the pattern at runtime; submitting unsubscribes
 * the old pattern before opening the new one (no leak). Buffer capped at
 * MAX_BUFFER=200 events to bound rendering cost (T-02-08-03).
 */
export function EventFeed() {
  const [pattern, setPattern] = useState<string>(DEFAULT_PATTERN);
  const [activePattern, setActivePattern] =
    useState<string>(DEFAULT_PATTERN);
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

  return (
    <section className="flex flex-col h-full min-h-0">
      <header className="flex items-center gap-2 p-2 border-b border-gray-200">
        <h2 className="text-sm font-semibold mr-2">Event feed</h2>
        <form onSubmit={applyPattern} className="flex gap-2 flex-1">
          <input
            aria-label="subject-pattern"
            className="flex-1 border rounded px-2 py-1 text-sm font-mono"
            value={pattern}
            onChange={(ev) => setPattern(ev.target.value)}
            placeholder="mesh.action.>"
          />
          <button
            type="submit"
            className="rounded bg-blue-600 text-white px-3 py-1 text-sm"
          >
            Subscribe
          </button>
        </form>
        <span className="text-xs text-gray-500">
          {events.length}/{MAX_BUFFER}
        </span>
      </header>
      {error && (
        <div className="p-2 text-sm text-red-700 bg-red-50">{error}</div>
      )}
      <ul className="overflow-auto flex-1 font-mono text-xs">
        {events.map((ev, i) => (
          <li
            key={`${ev.receivedAt}-${i}`}
            className="border-b border-gray-100 px-2 py-1"
          >
            <div className="flex justify-between text-gray-500">
              <span>{ev.subject}</span>
              <span>{new Date(ev.receivedAt).toLocaleTimeString()}</span>
            </div>
            <pre className="whitespace-pre-wrap break-all text-gray-800">
              {renderPayload(ev.payload, ev.raw)}
            </pre>
          </li>
        ))}
      </ul>
    </section>
  );
}
