"use client";

import { Field, Input, Select, Textarea } from "@/components/ui";
import type { FieldDef, LabelSchema, LabelValue } from "@/lib/types";

export type CodeOption = { code: string; label: string };

function visible(field: FieldDef, value: LabelValue): boolean {
  return !field.visible_if || value[field.visible_if.field] === field.visible_if.equals;
}

function optionsOf(field: FieldDef, codes: CodeOption[]): { value: string; label: string }[] {
  if (field.options_from === "reason_codes") return codes.map((c) => ({ value: c.code, label: `${c.code}: ${c.label}` }));
  return (field.options ?? []).map((o) => ({ value: o, label: VERDICT_LABEL[o] ?? o }));
}

const VERDICT_LABEL: Record<string, string> = {
  correct: "Đúng",
  incorrect: "Sai",
  unsure: "Không chắc",
};

const ACTIVE: Record<string, string> = {
  correct: "border-emerald-600 bg-emerald-600 text-white",
  incorrect: "border-red-600 bg-red-600 text-white",
  unsure: "border-amber-500 bg-amber-500 text-white",
};

/** Form built from a label schema; used by the annotator and the config preview. */
export function LabelForm({
  schema,
  value,
  onChange,
  codes,
  disabled,
}: {
  schema: LabelSchema;
  value: LabelValue;
  onChange: (next: LabelValue) => void;
  codes: CodeOption[];
  disabled?: boolean;
}) {
  const set = (name: string, v: unknown) => onChange({ ...value, [name]: v });

  return (
    <div className="flex flex-col gap-4">
      {schema.fields
        .filter((f) => visible(f, value))
        .map((f) => {
          const label = `${f.label ?? f.name}${f.required ? " *" : ""}`;
          if (f.type === "enum") {
            const options = optionsOf(f, codes);
            const isVerdict = options.every((o) => o.value in ACTIVE);
            return (
              <div key={f.name}>
                <p className="mb-2 text-sm font-medium">{label}</p>
                <div className={`grid gap-2 ${isVerdict ? "grid-cols-3" : "grid-cols-1"}`}>
                  {options.map((o) => (
                    <button
                      key={o.value}
                      type="button"
                      disabled={disabled}
                      onClick={() => set(f.name, o.value)}
                      className={`rounded-md border px-2 py-2 text-sm font-medium transition disabled:opacity-50 ${
                        value[f.name] === o.value
                          ? (ACTIVE[o.value] ?? "border-zinc-900 bg-zinc-900 text-white")
                          : "border-zinc-300 hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-900"
                      }`}
                    >
                      {o.label}
                    </button>
                  ))}
                </div>
              </div>
            );
          }
          if (f.type === "multi_select") {
            const selected = (value[f.name] as string[] | undefined) ?? [];
            return (
              <div key={f.name}>
                <p className="mb-2 text-sm font-medium">{label}</p>
                <div className="flex flex-col gap-1.5">
                  {optionsOf(f, codes).map((o) => (
                    <label key={o.value} className="flex cursor-pointer items-start gap-2 text-sm">
                      <input
                        type="checkbox"
                        className="mt-1"
                        disabled={disabled}
                        checked={selected.includes(o.value)}
                        onChange={() =>
                          set(f.name, selected.includes(o.value) ? selected.filter((s) => s !== o.value) : [...selected, o.value])
                        }
                      />
                      {o.label}
                    </label>
                  ))}
                </div>
              </div>
            );
          }
          if (f.type === "text") {
            return (
              <Field key={f.name} label={label}>
                <Textarea
                  rows={3}
                  maxLength={f.max_length}
                  disabled={disabled}
                  value={(value[f.name] as string | undefined) ?? ""}
                  onChange={(e) => set(f.name, e.target.value)}
                />
              </Field>
            );
          }
          if (f.type === "number") {
            return (
              <Field key={f.name} label={label}>
                <Input
                  type="number"
                  disabled={disabled}
                  value={(value[f.name] as number | undefined) ?? ""}
                  onChange={(e) => set(f.name, e.target.value === "" ? undefined : Number(e.target.value))}
                />
              </Field>
            );
          }
          return (
            <Field key={f.name} label={label}>
              <Select
                disabled={disabled}
                value={value[f.name] === undefined ? "" : String(value[f.name])}
                onChange={(e) => set(f.name, e.target.value === "" ? undefined : e.target.value === "true")}
              >
                <option value="">—</option>
                <option value="true">Có</option>
                <option value="false">Không</option>
              </Select>
            </Field>
          );
        })}
    </div>
  );
}

/** Whether a label satisfies the schema's required fields (client-side hint only). */
export function isLabelComplete(schema: LabelSchema, value: LabelValue | undefined): boolean {
  if (!value) return false;
  return schema.fields.every((f) => {
    if (!visible(f, value) || !f.required) return true;
    const v = value[f.name];
    return !(v === undefined || v === "" || (Array.isArray(v) && v.length === 0));
  });
}
