"use client";

import { type ReactNode } from "react";

import type { Step } from "@/lib/types";

const TITLES: Record<string, string> = {
  user: "User",
  thought: "Suy nghĩ của agent",
  tool_result: "Kết quả tool",
  assistant: "Agent trả lời",
  tool_call: "Tool call",
};

const STYLES: Record<string, string> = {
  user: "border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900",
  thought: "border-dashed border-zinc-300 text-zinc-500 italic dark:border-zinc-700",
  tool_result: "border-zinc-200 font-mono text-xs dark:border-zinc-800",
  assistant: "border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900",
};

type Props = {
  steps: Step[];
  compact?: boolean;
  selectedId?: string | null;
  onSelect?: (stepId: string) => void;
  /** Extra content under a tool call (label chip, review marks). */
  decorate?: (step: Extract<Step, { type: "tool_call" }>) => ReactNode;
  /** Highlight tone for a tool call step. */
  tone?: (stepId: string) => "ok" | "bad" | "warn" | null;
};

const TONES = {
  ok: "border-emerald-500",
  bad: "border-red-500",
  warn: "border-amber-500",
};

export function StepsView({ steps, compact, selectedId, onSelect, decorate, tone }: Props) {
  return (
    <ol className="flex flex-col gap-2">
      {steps.map((step) => {
        if (step.type === "tool_call") {
          const marked = tone?.(step.id);
          const selected = selectedId === step.id;
          const body = (
            <>
              <div className="mb-1 flex items-center gap-2 text-xs text-zinc-500">
                <span className="font-medium uppercase tracking-wide">{TITLES.tool_call}</span>
                <span className="font-mono">{step.id}</span>
              </div>
              <code className="font-mono text-sm font-semibold">{step.tool}</code>
              <pre className="mt-1 overflow-x-auto font-mono text-xs text-zinc-700 dark:text-zinc-300">
                {JSON.stringify(step.args, null, 2)}
              </pre>
              {decorate?.(step)}
            </>
          );
          const ring = selected
            ? "border-blue-500 ring-2 ring-blue-500/30"
            : marked
              ? `${TONES[marked]} border-2`
              : "border-zinc-300 dark:border-zinc-700";
          return (
            <li key={step.id}>
              {onSelect ? (
                <button
                  type="button"
                  onClick={() => onSelect(step.id)}
                  className={`w-full rounded-lg border p-3 text-left transition hover:border-zinc-400 ${ring}`}
                >
                  {body}
                </button>
              ) : (
                <div className={`rounded-lg border p-3 ${ring}`}>{body}</div>
              )}
            </li>
          );
        }
        const text = compact && step.content.length > 200 ? `${step.content.slice(0, 200)}…` : step.content;
        return (
          <li key={step.id} className={`rounded-lg border p-3 text-sm ${STYLES[step.type]}`}>
            <p className="mb-1 text-xs font-medium uppercase tracking-wide text-zinc-500 not-italic">
              {TITLES[step.type]}
            </p>
            <p className="break-words whitespace-pre-wrap">{text}</p>
          </li>
        );
      })}
    </ol>
  );
}
