import { useMemo, useState } from "react";
import { JsonSchema, resolveRef } from "../lib/registry";

// Schema-driven input form. Flat object schemas (string / number / boolean /
// enum fields) render as typed fields; anything nested falls back to a raw
// JSON editor so every invocable agent stays callable from the sandbox.
type Props = {
  schema: JsonSchema;
  disabled: boolean;
  onSubmit: (payload: unknown) => void;
  submitLabel: string;
};

type FieldSpec = {
  name: string;
  schema: JsonSchema;
  required: boolean;
};

function flatFields(schema: JsonSchema): FieldSpec[] | null {
  if (schema.type !== "object" || !schema.properties) return null;
  const required = new Set(schema.required ?? []);
  const fields: FieldSpec[] = [];
  for (const [name, raw] of Object.entries(schema.properties)) {
    const s = resolveRef(schema, raw);
    if (!s) return null;
    const t = s.type;
    const isEnum = Array.isArray(s.enum);
    if (!isEnum && t !== "string" && t !== "number" && t !== "integer" && t !== "boolean") {
      return null; // nested object/array → JSON fallback
    }
    fields.push({ name, schema: s, required: required.has(name) });
  }
  return fields;
}

function defaultsFor(fields: FieldSpec[]): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const f of fields) {
    if (f.schema.default !== undefined) out[f.name] = f.schema.default;
    else if (Array.isArray(f.schema.enum)) out[f.name] = f.schema.enum[0];
    else if (f.schema.type === "boolean") out[f.name] = false;
    else if (f.schema.type === "number" || f.schema.type === "integer") out[f.name] = 0;
    else out[f.name] = "";
  }
  return out;
}

function skeletonFor(schema: JsonSchema): string {
  // Best-effort example JSON for the fallback editor.
  const build = (s: JsonSchema | undefined, depth: number): unknown => {
    if (!s || depth > 4) return null;
    const r = resolveRef(schema, s) ?? s;
    if (r.default !== undefined) return r.default;
    if (Array.isArray(r.enum)) return r.enum[0];
    switch (r.type) {
      case "object": {
        const o: Record<string, unknown> = {};
        for (const [k, v] of Object.entries(r.properties ?? {})) o[k] = build(v, depth + 1);
        return o;
      }
      case "array":
        return [build(r.items, depth + 1)];
      case "string":
        return "";
      case "number":
      case "integer":
        return 0;
      case "boolean":
        return false;
      default:
        if (r.anyOf?.length) return build(r.anyOf[0], depth + 1);
        return null;
    }
  };
  return JSON.stringify(build(schema, 0), null, 2);
}

export function SchemaForm({ schema, disabled, onSubmit, submitLabel }: Props) {
  const fields = useMemo(() => flatFields(schema), [schema]);
  const [values, setValues] = useState<Record<string, unknown>>(() =>
    fields ? defaultsFor(fields) : {},
  );
  const [rawJson, setRawJson] = useState<string>(() => (fields ? "" : skeletonFor(schema)));
  const [rawError, setRawError] = useState<string | null>(null);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (fields) {
      onSubmit(values);
      return;
    }
    try {
      onSubmit(JSON.parse(rawJson));
      setRawError(null);
    } catch (err) {
      setRawError(`Invalid JSON: ${String(err)}`);
    }
  }

  if (!fields) {
    return (
      <form onSubmit={submit} className="space-y-2">
        <textarea
          aria-label="payload-json"
          className="w-full h-40 rounded border border-ink-700 bg-ink-950 p-2 font-mono text-xs text-ink-100 focus:border-ember-500 focus:outline-none"
          value={rawJson}
          onChange={(e) => setRawJson(e.target.value)}
          disabled={disabled}
          spellCheck={false}
        />
        {rawError && <p className="text-xs text-dead">{rawError}</p>}
        <SubmitButton disabled={disabled} label={submitLabel} />
      </form>
    );
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      {fields.map((f) => (
        <label key={f.name} className="block">
          <span className="microlabel">
            {f.name}
            {f.required && <span className="ml-1 text-ember-500">*</span>}
          </span>
          <FieldInput
            field={f}
            value={values[f.name]}
            disabled={disabled}
            onChange={(v) => setValues((prev) => ({ ...prev, [f.name]: v }))}
          />
          {f.schema.description && (
            <span className="mt-0.5 block text-[11px] text-ink-400">{f.schema.description}</span>
          )}
        </label>
      ))}
      <SubmitButton disabled={disabled} label={submitLabel} />
    </form>
  );
}

function FieldInput({
  field,
  value,
  disabled,
  onChange,
}: {
  field: FieldSpec;
  value: unknown;
  disabled: boolean;
  onChange: (v: unknown) => void;
}) {
  const base =
    "mt-1 w-full rounded border border-ink-700 bg-ink-950 px-2 py-1.5 text-sm text-ink-100 focus:border-ember-500 focus:outline-none disabled:opacity-50";
  const s = field.schema;

  if (Array.isArray(s.enum)) {
    return (
      <select
        className={base}
        value={String(value ?? "")}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      >
        {s.enum.map((opt) => (
          <option key={String(opt)} value={String(opt)}>
            {String(opt)}
          </option>
        ))}
      </select>
    );
  }
  if (s.type === "boolean") {
    return (
      <input
        type="checkbox"
        className="mt-1 h-4 w-4 accent-ember-500"
        checked={Boolean(value)}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
    );
  }
  if (s.type === "number" || s.type === "integer") {
    return (
      <input
        type="number"
        className={`${base} font-mono`}
        value={value === "" || value === undefined ? "" : Number(value)}
        disabled={disabled}
        step={s.type === "integer" ? 1 : "any"}
        onChange={(e) =>
          onChange(s.type === "integer" ? parseInt(e.target.value || "0", 10) : parseFloat(e.target.value || "0"))
        }
      />
    );
  }
  // Long free-text fields (e.g. the tasker's natural-language `text`) get a
  // textarea; short ids get a single-line input.
  const long = field.name === "text" || (s.maxLength ?? 0) > 120;
  if (long) {
    return (
      <textarea
        className={`${base} h-20 resize-y`}
        value={String(value ?? "")}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        placeholder={s.description}
      />
    );
  }
  return (
    <input
      type="text"
      className={`${base} font-mono`}
      value={String(value ?? "")}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

function SubmitButton({ disabled, label }: { disabled: boolean; label: string }) {
  return (
    <button
      type="submit"
      disabled={disabled}
      className="rounded bg-ember-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-ember-500 disabled:cursor-not-allowed disabled:opacity-40"
    >
      {label}
    </button>
  );
}
