import { useEffect, useRef, useState } from "react";
import type { TapEvent } from "@openagentmesh/sdk";
import { useMesh } from "../MeshProvider";
import { prettyJson } from "../lib/format";

interface FeedRow extends TapEvent {
  id: number;
  receivedAt: string;
}

/** Oldest rows are dropped past this cap so an unattended feed can't grow unbounded. */
const MAX_ROWS = 500;

function rowPayload(row: FeedRow): string {
  return typeof row.payload === "string" ? row.payload : prettyJson(row.payload);
}

/**
 * Event feed (ADR-0056): wiretap on a user-supplied subject pattern via the
 * SDK's `tap()`. Pause buffers arrivals (the subscription stays open) and
 * resume flushes the buffer; unsubscribe aborts the tap.
 */
export default function Events() {
  const { mesh } = useMesh();
  const [pattern, setPattern] = useState("mesh.>");
  const [subscribed, setSubscribed] = useState(false);
  const [paused, setPaused] = useState(false);
  const [rows, setRows] = useState<FeedRow[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const bufferRef = useRef<FeedRow[]>([]);
  const pausedRef = useRef(false);
  const nextId = useRef(0);

  // Abort the live tap when the screen unmounts.
  useEffect(() => () => abortRef.current?.abort(), []);

  const append = (batch: FeedRow[]) => {
    setRows((prev) => {
      const merged = [...prev, ...batch];
      return merged.length > MAX_ROWS ? merged.slice(merged.length - MAX_ROWS) : merged;
    });
  };

  const subscribe = () => {
    if (!mesh || subscribed) return;
    const abort = new AbortController();
    abortRef.current = abort;
    setSubscribed(true);
    void (async () => {
      try {
        for await (const event of mesh.tap(pattern, { signal: abort.signal })) {
          const row: FeedRow = {
            ...event,
            id: nextId.current++,
            receivedAt: new Date().toLocaleTimeString(),
          };
          if (pausedRef.current) bufferRef.current.push(row);
          else append([row]);
        }
      } catch {
        /* aborted (unsubscribe/unmount) or the connection dropped */
      } finally {
        if (abortRef.current === abort) {
          abortRef.current = null;
          setSubscribed(false);
        }
      }
    })();
  };

  const unsubscribe = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setSubscribed(false);
    setPaused(false);
    pausedRef.current = false;
    bufferRef.current = [];
  };

  const togglePause = () => {
    if (paused) {
      const buffered = bufferRef.current;
      bufferRef.current = [];
      pausedRef.current = false;
      setPaused(false);
      if (buffered.length > 0) append(buffered);
    } else {
      pausedRef.current = true;
      setPaused(true);
    }
  };

  return (
    <div className="space-y-4">
      <form
        className="flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          subscribe();
        }}
      >
        <label className="flex-1">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
            Subject pattern
          </span>
          <input
            type="text"
            aria-label="Subject pattern"
            value={pattern}
            onChange={(e) => setPattern(e.target.value)}
            disabled={subscribed}
            className="w-full rounded border border-slate-300 bg-white px-3 py-1.5 font-mono text-sm disabled:bg-slate-100 disabled:text-slate-500"
          />
        </label>
        {subscribed ? (
          <button
            type="button"
            onClick={unsubscribe}
            className="rounded border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100"
          >
            Unsubscribe
          </button>
        ) : (
          <button
            type="submit"
            className="rounded bg-slate-900 px-3 py-1.5 text-sm font-medium text-white"
          >
            Subscribe
          </button>
        )}
        <button
          type="button"
          onClick={togglePause}
          disabled={!subscribed}
          className="rounded border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50"
        >
          {paused ? "Resume" : "Pause"}
        </button>
        <button
          type="button"
          onClick={() => setRows([])}
          className="rounded border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100"
        >
          Clear
        </button>
      </form>

      {rows.length === 0 ? (
        <p className="text-sm text-slate-500">
          {subscribed ? "Waiting for events…" : "Subscribe to start tapping the mesh."}
        </p>
      ) : (
        <ul className="space-y-1">
          {rows.map((row) => (
            <li
              key={row.id}
              className={`rounded border p-2 text-xs ${
                row.isError ? "border-red-200 bg-red-50" : "border-slate-200 bg-white"
              }`}
            >
              <div className="mb-1 flex items-center gap-2">
                <span className="text-slate-400">{row.receivedAt}</span>
                <span className="font-mono font-medium text-slate-700">{row.subject}</span>
                {row.isError && (
                  <span className="rounded bg-red-100 px-1.5 py-0.5 font-mono font-semibold text-red-800">
                    error
                  </span>
                )}
              </div>
              <pre className="overflow-x-auto font-mono leading-relaxed text-slate-600">{rowPayload(row)}</pre>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
