import { MeshError } from "./errors.js";

/** Error raised when a stream/subscribe is cancelled via AbortSignal. */
export class AbortError extends MeshError {
  static code = "aborted";
  constructor(message = "operation aborted") {
    super(message, { code: AbortError.code });
    this.name = "AbortError";
  }
}

/**
 * Race a promise against a deadline and an optional AbortSignal. On timeout the
 * `onTimeout` factory supplies the rejection; on abort an `AbortError` rejects.
 * The original promise is abandoned (callers unsubscribe in a `finally`).
 */
export function withDeadline<T>(
  p: Promise<T>,
  ms: number,
  onTimeout: () => Error,
  signal?: AbortSignal,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => {
      cleanup();
      reject(onTimeout());
    }, ms);
    const onAbort = () => {
      cleanup();
      reject(new AbortError());
    };
    const cleanup = () => {
      clearTimeout(timer);
      if (signal) signal.removeEventListener("abort", onAbort);
    };
    if (signal) {
      if (signal.aborted) {
        cleanup();
        reject(new AbortError());
        return;
      }
      signal.addEventListener("abort", onAbort);
    }
    p.then(
      (v) => {
        cleanup();
        resolve(v);
      },
      (e) => {
        cleanup();
        reject(e);
      },
    );
  });
}

/** Race a promise against an AbortSignal only (no timeout). */
export function withAbort<T>(p: Promise<T>, signal?: AbortSignal): Promise<T> {
  if (!signal) return p;
  return new Promise<T>((resolve, reject) => {
    const onAbort = () => {
      signal.removeEventListener("abort", onAbort);
      reject(new AbortError());
    };
    if (signal.aborted) return reject(new AbortError());
    signal.addEventListener("abort", onAbort);
    p.then(
      (v) => {
        signal.removeEventListener("abort", onAbort);
        resolve(v);
      },
      (e) => {
        signal.removeEventListener("abort", onAbort);
        reject(e);
      },
    );
  });
}

export function errName(err: unknown): string {
  return (err as { name?: string } | undefined)?.name ?? "";
}

export function isTimeoutError(err: unknown): boolean {
  const n = errName(err);
  if (n === "TimeoutError") return true;
  const msg = (err as Error | undefined)?.message ?? "";
  return n === "RequestError" && /timed out|timeout/i.test(msg);
}

export function isNoRespondersError(err: unknown): boolean {
  if (errName(err) === "NoRespondersError") return true;
  const msg = (err as Error | undefined)?.message ?? "";
  return /no responders/i.test(msg);
}
