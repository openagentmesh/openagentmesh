// Typed error hierarchy mirroring the OAM wire envelope (ADR-0057).
// Wire body: { code, message, agent, request_id, details } with X-Mesh-Status: error.

export interface ErrorEnvelope {
  code?: string;
  message?: string;
  agent?: string;
  request_id?: string;
  details?: Record<string, unknown>;
}

export class MeshError extends Error {
  /** Stable wire code; overridden per subclass. */
  static code = "mesh_error";
  readonly code: string;
  readonly agent?: string;
  readonly requestId?: string;
  readonly details: Record<string, unknown>;

  constructor(
    message: string,
    opts: { code?: string; agent?: string; requestId?: string; details?: Record<string, unknown> } = {},
  ) {
    super(message);
    this.name = new.target.name;
    this.code = opts.code ?? (new.target as typeof MeshError).code;
    this.agent = opts.agent;
    this.requestId = opts.requestId;
    this.details = opts.details ?? {};
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class InvalidInput extends MeshError {
  static code = "invalid_input";
}
export class HandlerError extends MeshError {
  static code = "handler_error";
}
export class InvocationMismatch extends MeshError {
  static code = "invocation_mismatch";
}
export class NotFound extends MeshError {
  static code = "not_found";
}
export class ConnectionFailed extends MeshError {
  static code = "connection_failed";
}

export class MeshTimeout extends MeshError {
  static code = "timeout";
  readonly subject?: string;
  readonly timeout?: number;
  constructor(
    message: string,
    opts: { agent?: string; requestId?: string; details?: Record<string, unknown>; subject?: string; timeout?: number } = {},
  ) {
    super(message, { ...opts, code: MeshTimeout.code });
    this.subject = opts.subject;
    this.timeout = opts.timeout;
  }
}

export class ChunkSequenceError extends MeshError {
  static code = "chunk_sequence_error";
  readonly expectedSeq?: number;
  readonly gotSeq?: number;
  constructor(
    message: string,
    opts: { agent?: string; requestId?: string; expectedSeq?: number; gotSeq?: number } = {},
  ) {
    super(message, {
      code: ChunkSequenceError.code,
      agent: opts.agent,
      requestId: opts.requestId,
      details: { expected_seq: opts.expectedSeq, got_seq: opts.gotSeq },
    });
    this.expectedSeq = opts.expectedSeq;
    this.gotSeq = opts.gotSeq;
  }
}

export class KVKeyExists extends MeshError {
  static code = "kv_key_exists";
  readonly key?: string;
  constructor(message: string, opts: { key?: string } = {}) {
    super(message, { code: KVKeyExists.code, details: { key: opts.key } });
    this.key = opts.key;
  }
}

// Only base-signature classes; MeshTimeout/ChunkSequenceError/KVKeyExists have
// bespoke constructors and are handled explicitly in `fromEnvelope`.
type BaseErrorCtor = new (
  message: string,
  opts?: { code?: string; agent?: string; requestId?: string; details?: Record<string, unknown> },
) => MeshError;

const CODE_TO_CLASS: Record<string, BaseErrorCtor> = {
  [InvalidInput.code]: InvalidInput,
  [HandlerError.code]: HandlerError,
  [InvocationMismatch.code]: InvocationMismatch,
  [NotFound.code]: NotFound,
  [ConnectionFailed.code]: ConnectionFailed,
};

/**
 * Reconstruct a typed error from a wire envelope. Unknown codes fall back to a
 * base `MeshError` with the code preserved (forward compatibility).
 */
export function fromEnvelope(env: ErrorEnvelope): MeshError {
  const code = env.code ?? MeshError.code;
  const message = env.message ?? "mesh error";
  const common = { agent: env.agent, requestId: env.request_id, details: env.details ?? {} };

  switch (code) {
    case MeshTimeout.code:
      return new MeshTimeout(message, {
        ...common,
        subject: env.details?.["subject"] as string | undefined,
        timeout: env.details?.["timeout"] as number | undefined,
      });
    case ChunkSequenceError.code:
      return new ChunkSequenceError(message, {
        agent: env.agent,
        requestId: env.request_id,
        expectedSeq: env.details?.["expected_seq"] as number | undefined,
        gotSeq: env.details?.["got_seq"] as number | undefined,
      });
    case KVKeyExists.code:
      return new KVKeyExists(message, { key: env.details?.["key"] as string | undefined });
    default: {
      const Cls = CODE_TO_CLASS[code] ?? MeshError;
      return new Cls(message, { ...common, code });
    }
  }
}
