"use client";

import { useMemo, useState } from "react";

import {
  REASON_CODES,
  type DemoJob,
  type Step,
  type Verdict,
} from "@/lib/mock-trajectory";

type Label = {
  verdict: Verdict | null;
  reasonCodes: string[];
  note: string;
};

const EMPTY_LABEL: Label = { verdict: null, reasonCodes: [], note: "" };

const VERDICTS: { value: Verdict; label: string; active: string }[] = [
  {
    value: "correct",
    label: "Đúng",
    active: "border-emerald-600 bg-emerald-600 text-white",
  },
  {
    value: "incorrect",
    label: "Sai",
    active: "border-red-600 bg-red-600 text-white",
  },
  {
    value: "unsure",
    label: "Không chắc",
    active: "border-amber-500 bg-amber-500 text-white",
  },
];

const VERDICT_DOT: Record<Verdict, string> = {
  correct: "bg-emerald-500",
  incorrect: "bg-red-500",
  unsure: "bg-amber-500",
};

function isComplete(label: Label | undefined): boolean {
  if (!label?.verdict) return false;
  if (label.verdict === "incorrect") return label.reasonCodes.length > 0;
  return true;
}

export function ToolCallAnnotator({ job }: { job: DemoJob }) {
  const toolCalls = useMemo(
    () =>
      job.steps.filter(
        (s): s is Extract<Step, { type: "tool_call" }> => s.type === "tool_call",
      ),
    [job],
  );

  const [labels, setLabels] = useState<Record<string, Label>>({});
  const [selectedId, setSelectedId] = useState<string>(toolCalls[0]?.id ?? "");
  const [checks, setChecks] = useState<boolean[]>(() =>
    job.guideline.map(() => false),
  );
  const [submitted, setSubmitted] = useState(false);

  const selectedIndex = toolCalls.findIndex((c) => c.id === selectedId);
  const selected = toolCalls[selectedIndex];
  const label = labels[selectedId] ?? EMPTY_LABEL;

  const doneCount = toolCalls.filter((c) => isComplete(labels[c.id])).length;
  const allDone = doneCount === toolCalls.length;
  const allChecked = checks.every(Boolean);

  function update(patch: Partial<Label>) {
    setLabels((prev) => ({
      ...prev,
      [selectedId]: { ...(prev[selectedId] ?? EMPTY_LABEL), ...patch },
    }));
  }

  function setVerdict(verdict: Verdict) {
    update({
      verdict,
      reasonCodes: verdict === "incorrect" ? label.reasonCodes : [],
    });
  }

  function toggleReason(code: string) {
    update({
      reasonCodes: label.reasonCodes.includes(code)
        ? label.reasonCodes.filter((c) => c !== code)
        : [...label.reasonCodes, code],
    });
  }

  function go(offset: number) {
    const next = toolCalls[selectedIndex + offset];
    if (next) setSelectedId(next.id);
  }

  const result = {
    job_id: job.id,
    guideline_version: job.guidelineVersion,
    annotations: toolCalls.map((c) => ({
      item_id: c.id,
      tool: c.tool,
      ...(labels[c.id] ?? EMPTY_LABEL),
    })),
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="flex flex-wrap items-center gap-x-6 gap-y-2 border-b border-zinc-200 px-6 py-3 dark:border-zinc-800">
        <div>
          <p className="text-xs text-zinc-500">{job.project}</p>
          <h1 className="text-base font-semibold">{job.id}</h1>
        </div>
        <span className="rounded-full border border-zinc-200 px-2.5 py-0.5 text-xs text-zinc-500 dark:border-zinc-800">
          Guideline {job.guidelineVersion}
        </span>
        <div className="ml-auto flex items-center gap-3 text-sm">
          <span className="text-zinc-500">
            {doneCount}/{toolCalls.length} tool call đã gán nhãn
          </span>
          <div className="h-1.5 w-32 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
            <div
              className="h-full bg-emerald-500 transition-all"
              style={{ width: `${(doneCount / toolCalls.length) * 100}%` }}
            />
          </div>
        </div>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[1fr_380px]">
        <section className="overflow-y-auto px-6 py-5">
          <details className="mb-5 rounded-lg border border-zinc-200 p-3 text-sm dark:border-zinc-800">
            <summary className="cursor-pointer font-medium">
              Tool có sẵn cho agent ({job.tools.length})
            </summary>
            <ul className="mt-3 flex flex-col gap-3">
              {job.tools.map((t) => (
                <li key={t.name}>
                  <code className="font-mono font-semibold">{t.name}</code>
                  <span className="text-zinc-500"> — {t.description}</span>
                  <ul className="mt-1 ml-4 list-disc font-mono text-xs text-zinc-600 dark:text-zinc-400">
                    {t.params.map((p) => (
                      <li key={p.name}>
                        {p.name}: {p.type}
                        {p.required ? " *" : ""}
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          </details>

          <ol className="flex flex-col gap-3">
            {job.steps.map((step) => (
              <StepView
                key={step.id}
                step={step}
                selected={step.id === selectedId}
                verdict={labels[step.id]?.verdict ?? null}
                onSelect={() => setSelectedId(step.id)}
              />
            ))}
          </ol>
        </section>

        <aside className="flex min-h-0 flex-col gap-5 overflow-y-auto border-t border-zinc-200 p-5 lg:border-t-0 lg:border-l dark:border-zinc-800">
          {selected ? (
            <>
              <div>
                <p className="text-xs text-zinc-500">
                  Tool call {selectedIndex + 1}/{toolCalls.length}
                </p>
                <p className="font-mono text-sm font-semibold">
                  {selected.tool}
                </p>
              </div>

              <div>
                <p className="mb-2 text-sm font-medium">Tool call này…</p>
                <div className="grid grid-cols-3 gap-2">
                  {VERDICTS.map((v) => (
                    <button
                      key={v.value}
                      type="button"
                      onClick={() => setVerdict(v.value)}
                      className={`rounded-md border px-2 py-2 text-sm font-medium transition ${
                        label.verdict === v.value
                          ? v.active
                          : "border-zinc-300 hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-900"
                      }`}
                    >
                      {v.label}
                    </button>
                  ))}
                </div>
              </div>

              {label.verdict === "incorrect" && (
                <div>
                  <p className="mb-2 text-sm font-medium">
                    Lý do <span className="text-red-600">*</span>
                  </p>
                  <div className="flex flex-col gap-1.5">
                    {REASON_CODES.map((r) => (
                      <label
                        key={r.code}
                        className="flex cursor-pointer items-start gap-2 text-sm"
                      >
                        <input
                          type="checkbox"
                          className="mt-1"
                          checked={label.reasonCodes.includes(r.code)}
                          onChange={() => toggleReason(r.code)}
                        />
                        <span>
                          <code className="font-mono text-xs">{r.code}</code>
                          <span className="block text-zinc-500">{r.label}</span>
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              )}

              <div>
                <label className="mb-2 block text-sm font-medium" htmlFor="note">
                  Ghi chú
                  {label.verdict === "unsure" && (
                    <span className="font-normal text-zinc-500">
                      {" "}
                      (nên ghi để reviewer biết)
                    </span>
                  )}
                </label>
                <textarea
                  id="note"
                  rows={3}
                  value={label.note}
                  onChange={(e) => update({ note: e.target.value })}
                  className="w-full rounded-md border border-zinc-300 bg-transparent p-2 text-sm dark:border-zinc-700"
                />
              </div>

              <div className="flex justify-between">
                <button
                  type="button"
                  onClick={() => go(-1)}
                  disabled={selectedIndex === 0}
                  className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm disabled:opacity-40 dark:border-zinc-700"
                >
                  ← Trước
                </button>
                <button
                  type="button"
                  onClick={() => go(1)}
                  disabled={selectedIndex === toolCalls.length - 1}
                  className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm disabled:opacity-40 dark:border-zinc-700"
                >
                  Sau →
                </button>
              </div>
            </>
          ) : (
            <p className="text-sm text-zinc-500">
              Chọn một tool call bên trái để gán nhãn.
            </p>
          )}

          <hr className="border-zinc-200 dark:border-zinc-800" />

          <div>
            <p className="mb-2 text-sm font-medium">Self-check trước khi submit</p>
            <ul className="flex flex-col gap-1.5">
              {job.guideline.map((rule, i) => (
                <li key={rule}>
                  <label className="flex cursor-pointer items-start gap-2 text-xs text-zinc-600 dark:text-zinc-400">
                    <input
                      type="checkbox"
                      className="mt-0.5"
                      checked={checks[i]}
                      onChange={() =>
                        setChecks((prev) =>
                          prev.map((v, j) => (j === i ? !v : v)),
                        )
                      }
                    />
                    {rule}
                  </label>
                </li>
              ))}
            </ul>
          </div>

          <button
            type="button"
            disabled={!allDone || !allChecked}
            onClick={() => setSubmitted(true)}
            className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
          >
            Submit job
          </button>
          {!allDone && (
            <p className="-mt-3 text-xs text-zinc-500">
              Cần gán nhãn đủ {toolCalls.length} tool call.
            </p>
          )}

          {submitted && (
            <div>
              <p className="mb-2 text-sm font-medium">
                Kết quả sẽ gửi lên (annotation_json)
              </p>
              <pre className="max-h-64 overflow-auto rounded-md bg-zinc-100 p-3 font-mono text-xs dark:bg-zinc-900">
                {JSON.stringify(result, null, 2)}
              </pre>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

function StepView({
  step,
  selected,
  verdict,
  onSelect,
}: {
  step: Step;
  selected: boolean;
  verdict: Verdict | null;
  onSelect: () => void;
}) {
  if (step.type === "tool_call") {
    return (
      <li>
        <button
          type="button"
          onClick={onSelect}
          className={`w-full rounded-lg border p-3 text-left transition ${
            selected
              ? "border-blue-500 ring-2 ring-blue-500/30"
              : "border-zinc-300 hover:border-zinc-400 dark:border-zinc-700"
          }`}
        >
          <div className="mb-1 flex items-center gap-2 text-xs text-zinc-500">
            <span className="font-medium uppercase tracking-wide">
              Tool call
            </span>
            {verdict && (
              <span
                className={`h-2 w-2 rounded-full ${VERDICT_DOT[verdict]}`}
                aria-label={verdict}
              />
            )}
          </div>
          <code className="font-mono text-sm font-semibold">{step.tool}</code>
          <pre className="mt-1 overflow-x-auto font-mono text-xs text-zinc-700 dark:text-zinc-300">
            {JSON.stringify(step.args, null, 2)}
          </pre>
        </button>
      </li>
    );
  }

  const style: Record<string, string> = {
    user: "border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900",
    thought:
      "border-dashed border-zinc-300 text-zinc-500 italic dark:border-zinc-700",
    tool_result: "border-zinc-200 font-mono text-xs dark:border-zinc-800",
    assistant:
      "border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900",
  };
  const title: Record<string, string> = {
    user: "User",
    thought: "Suy nghĩ của agent",
    tool_result: "Kết quả tool",
    assistant: "Agent trả lời",
  };

  return (
    <li className={`rounded-lg border p-3 text-sm ${style[step.type]}`}>
      <p className="mb-1 text-xs font-medium uppercase tracking-wide text-zinc-500 not-italic">
        {title[step.type]}
      </p>
      <p className="break-words">{step.content}</p>
    </li>
  );
}
