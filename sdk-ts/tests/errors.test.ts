import { describe, expect, it } from "vitest";
import {
  ChunkSequenceError,
  fromEnvelope,
  InvocationMismatch,
  KVKeyExists,
  MeshError,
  MeshTimeout,
  NotFound,
} from "../src/index.js";

describe("error taxonomy", () => {
  it("maps wire codes to typed classes", () => {
    expect(fromEnvelope({ code: "not_found", message: "x", agent: "a" })).toBeInstanceOf(NotFound);
    expect(fromEnvelope({ code: "invocation_mismatch", message: "x" })).toBeInstanceOf(InvocationMismatch);
    expect(fromEnvelope({ code: "invalid_input", message: "x" }).code).toBe("invalid_input");
  });

  it("falls back to MeshError preserving an unknown code", () => {
    const e = fromEnvelope({ code: "future_code", message: "m" });
    expect(e).toBeInstanceOf(MeshError);
    expect(e.code).toBe("future_code");
    expect(e.message).toBe("m");
  });

  it("reconstructs a timeout error without reading a unit-ambiguous duration", () => {
    // The wire envelope carries no structured timeout (Python serializes
    // details={}); the value lives only in `message`. We must not interpret a
    // details.timeout, whose unit the two SDKs disagree on. See ADR-0057.
    const e = fromEnvelope({ code: "timeout", message: "No message on mesh.agent.x within 30.0s", details: { timeout: 30 } });
    expect(e).toBeInstanceOf(MeshTimeout);
    expect(e.code).toBe("timeout");
    expect(e.message).toContain("within 30.0s");
    expect((e as MeshTimeout).timeout).toBeUndefined();
    expect((e as MeshTimeout).subject).toBeUndefined();
  });

  it("reconstructs ChunkSequenceError expected/got", () => {
    const e = fromEnvelope({ code: "chunk_sequence_error", message: "seq", details: { expected_seq: 2, got_seq: 5 } });
    expect(e).toBeInstanceOf(ChunkSequenceError);
    expect((e as ChunkSequenceError).expectedSeq).toBe(2);
    expect((e as ChunkSequenceError).gotSeq).toBe(5);
  });

  it("reconstructs KVKeyExists key", () => {
    const e = fromEnvelope({ code: "kv_key_exists", message: "exists", details: { key: "k1" } });
    expect(e).toBeInstanceOf(KVKeyExists);
    expect((e as KVKeyExists).key).toBe("k1");
  });

  it("every subclass is an instanceof MeshError and carries fields", () => {
    const e = new NotFound("nope", { agent: "a", requestId: "r1" });
    expect(e).toBeInstanceOf(MeshError);
    expect(e).toBeInstanceOf(Error);
    expect(e.agent).toBe("a");
    expect(e.requestId).toBe("r1");
    expect(e.code).toBe("not_found");
  });
});
