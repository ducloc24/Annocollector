"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { isLabelComplete, LabelForm } from "@/components/label-form";
import { StepsView } from "@/components/step-view";
import { Badge, Button, Modal, Notice, Spinner, formatDate } from "@/components/ui";
import { ApiError, errorMessage, get, post, put } from "@/lib/api";
import type { JobItem, JobView, LabelValue, Step } from "@/lib/types";

/** Draft shape saved on the job: { [item_id]: { [target]: label } } */
type Draft = Record<string, Record<string, LabelValue>>;

function ToolList({ item }: { item: JobItem }) {
  if (item.payload.tools.length === 0) return null;
  return (
    <details className="mb-4 rounded-lg border border-zinc-200 p-3 text-sm dark:border-zinc-800">
      <summary className="cursor-pointer font-medium">Tool có sẵn cho agent ({item.payload.tools.length})</summary>
      <ul className="mt-2 flex flex-col gap-1 font-mono text-xs">
        {item.payload.tools.map((t, i) => (
          <li key={i}>
            <strong>{t.name}</strong> {t.params ? JSON.stringify(t.params) : ""}
          </li>
        ))}
      </ul>
    </details>
  );
}

export default function AnnotatePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [view, setView] = useState<JobView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>({});
  const [itemIndex, setItemIndex] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [checks, setChecks] = useState<boolean[]>([]);
  const [showGuideline, setShowGuideline] = useState(false);
  const [saving, setSaving] = useState<"idle" | "saving" | "saved">("idle");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState<{ round: number } | null>(null);
  const [problems, setProblems] = useState<string[]>([]);
  const dirty = useRef(false);

  useEffect(() => {
    (async () => {
      try {
        let v = await get<JobView>(`/jobs/${id}`);
        if (v.job.status === "assigned" || v.job.status === "rejected") {
          await post(`/jobs/${id}/start`);
          v = await get<JobView>(`/jobs/${id}`);
        }
        setView(v);
        setDraft((v.draft as Draft | null) ?? {});
        setChecks(v.config.self_check.map(() => false));
        const first = v.items[0]?.payload.targets[0] ?? null;
        setSelected(first);
      } catch (e) {
        setError(errorMessage(e));
      }
    })();
  }, [id]);

  const schema = view?.config.label_schema;
  const codes = useMemo(
    () => (view?.reason_codes ?? []).filter((c) => c.applies_to !== "review"),
    [view],
  );
  const item = view?.items[itemIndex];
  const readOnly = view?.job.status !== "in_progress";

  const allTargets = useMemo(
    () => (view?.items ?? []).flatMap((i) => i.payload.targets.map((t) => ({ item: i.id, target: t }))),
    [view],
  );
  const labelOf = (itemId: string, target: string) => draft[itemId]?.[target];
  const doneCount = schema ? allTargets.filter((t) => isLabelComplete(schema, labelOf(t.item, t.target))).length : 0;
  const allDone = allTargets.length > 0 && doneCount === allTargets.length;
  const errorsByTarget = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const e of view?.last_review?.errors ?? []) {
      const key = `${e.item_id}:${e.target}`;
      map.set(key, [...(map.get(key) ?? []), `${e.reason_code}${e.note ? `: ${e.note}` : ""}`]);
    }
    return map;
  }, [view]);

  const save = useCallback(async () => {
    if (!dirty.current || readOnly) return;
    setSaving("saving");
    try {
      await put(`/jobs/${id}/draft`, { draft });
      dirty.current = false;
      setSaving("saved");
    } catch (e) {
      if (e instanceof ApiError && e.code === "lease_expired") {
        setError("Job đã hết thời gian giữ và được trả về hàng đợi.");
      }
      setSaving("idle");
    }
  }, [draft, id, readOnly]);

  // Auto-save a moment after the last change.
  useEffect(() => {
    if (!dirty.current) return;
    const timer = setTimeout(() => void save(), 1500);
    return () => clearTimeout(timer);
  }, [draft, save]);

  function setLabel(itemId: string, target: string, value: LabelValue) {
    dirty.current = true;
    setSaving("idle");
    setDraft((d) => ({ ...d, [itemId]: { ...(d[itemId] ?? {}), [target]: value } }));
  }

  async function submit() {
    if (!view) return;
    setSubmitting(true);
    setProblems([]);
    try {
      await save();
      const annotations = allTargets.map((t) => ({
        item_id: t.item,
        target: t.target,
        value: labelOf(t.item, t.target) ?? {},
      }));
      const result = await post<{ round: number }>(`/jobs/${id}/submit`, { annotations, self_check: checks });
      setDone(result);
    } catch (e) {
      const details = e instanceof ApiError ? (e.details as { errors?: string[] } | undefined) : undefined;
      setProblems(details?.errors ?? [errorMessage(e)]);
      setSubmitting(false);
    }
  }

  if (error) {
    return (
      <div className="mx-auto mt-20 flex max-w-md flex-col gap-4 px-4">
        <Notice>{error}</Notice>
        <Link href="/work" className="text-sm underline underline-offset-2">
          Về hàng đợi
        </Link>
      </div>
    );
  }
  if (!view || !schema || !item) return <Spinner />;

  const steps = item.payload.steps as Step[];
  const targetIndex = allTargets.findIndex((t) => t.item === item.id && t.target === selected);

  function go(offset: number) {
    const next = allTargets[targetIndex + offset];
    if (!next) return;
    const nextItem = view!.items.findIndex((i) => i.id === next.item);
    setItemIndex(nextItem);
    setSelected(next.target);
  }

  const selectedErrors = selected ? errorsByTarget.get(`${item.id}:${selected}`) : undefined;

  return (
    <>
      <header className="flex flex-wrap items-center gap-x-5 gap-y-2 border-b border-zinc-200 px-5 py-3 dark:border-zinc-800">
        <Link href="/work" className="text-sm text-zinc-500 underline underline-offset-2">
          ← Thoát
        </Link>
        <div>
          <p className="text-xs text-zinc-500">{view.task.name}</p>
          <h1 className="text-base font-semibold">Job #{view.job.ordinal}</h1>
        </div>
        <button type="button" onClick={() => setShowGuideline(true)} className="rounded-full border border-zinc-200 px-2.5 py-0.5 text-xs text-zinc-600 hover:bg-zinc-100 dark:border-zinc-800 dark:text-zinc-400 dark:hover:bg-zinc-900">
          Guideline v{view.guideline.version}
        </button>
        {view.job.lease_expires_at && <span className="text-xs text-zinc-500">giữ đến {formatDate(view.job.lease_expires_at)}</span>}
        <span className="text-xs text-zinc-500">
          {saving === "saving" ? "Đang lưu nháp…" : saving === "saved" ? "Đã lưu nháp" : ""}
        </span>
        <div className="ml-auto flex items-center gap-3 text-sm">
          <span className="text-zinc-500">
            {doneCount}/{allTargets.length} tool call đã gán nhãn
          </span>
          <div className="h-1.5 w-32 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
            <div className="h-full bg-emerald-500 transition-all" style={{ width: `${allTargets.length ? (doneCount / allTargets.length) * 100 : 0}%` }} />
          </div>
        </div>
      </header>

      {view.last_review && (
        <div className="border-b border-red-200 bg-red-50 px-5 py-2 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          Job bị trả lại: {view.last_review.reason ?? "xem các bước được đánh dấu đỏ"}. Còn {view.rework_remaining} lượt sửa.
        </div>
      )}

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[1fr_380px]">
        <section className="overflow-y-auto px-5 py-5">
          {view.items.length > 1 && (
            <div className="mb-4 flex flex-wrap gap-2">
              {view.items.map((it, i) => (
                <Button key={it.id} variant={i === itemIndex ? "primary" : "secondary"} onClick={() => { setItemIndex(i); setSelected(it.payload.targets[0] ?? null); }}>
                  Item {i + 1}
                </Button>
              ))}
            </div>
          )}
          <ToolList item={item} />
          <StepsView
            steps={steps}
            selectedId={selected}
            onSelect={setSelected}
            tone={(stepId) => {
              if (errorsByTarget.has(`${item.id}:${stepId}`)) return "bad";
              return isLabelComplete(schema, labelOf(item.id, stepId)) ? "ok" : null;
            }}
            decorate={(step) => {
              const label = labelOf(item.id, step.id);
              const bad = errorsByTarget.get(`${item.id}:${step.id}`);
              return (
                <>
                  {label?.verdict !== undefined && (
                    <div className="mt-2">
                      <Badge>{String(label.verdict)}</Badge>
                    </div>
                  )}
                  {bad && <p className="mt-2 text-xs text-red-600">Reviewer: {bad.join("; ")}</p>}
                </>
              );
            }}
          />
        </section>

        <aside className="flex min-h-0 flex-col gap-5 overflow-y-auto border-t border-zinc-200 p-5 dark:border-zinc-800 lg:border-t-0 lg:border-l">
          {selected ? (
            <>
              <div>
                <p className="text-xs text-zinc-500">
                  Tool call {targetIndex + 1}/{allTargets.length}
                </p>
                <p className="font-mono text-sm font-semibold">{(steps.find((s) => s.id === selected) as { tool?: string })?.tool}</p>
              </div>
              {selectedErrors && (
                <Notice>
                  Reviewer ghi: {selectedErrors.join("; ")}
                </Notice>
              )}
              <LabelForm
                schema={schema}
                value={labelOf(item.id, selected) ?? {}}
                onChange={(v) => setLabel(item.id, selected, v)}
                codes={codes}
                disabled={readOnly}
              />
              <div className="flex justify-between">
                <Button disabled={targetIndex <= 0} onClick={() => go(-1)}>
                  ← Trước
                </Button>
                <Button disabled={targetIndex >= allTargets.length - 1} onClick={() => go(1)}>
                  Sau →
                </Button>
              </div>
            </>
          ) : (
            <p className="text-sm text-zinc-500">Chọn một tool call bên trái để gán nhãn.</p>
          )}

          <hr className="border-zinc-200 dark:border-zinc-800" />

          {view.config.self_check.length > 0 && (
            <div>
              <p className="mb-2 text-sm font-medium">Self-check trước khi nộp</p>
              <ul className="flex flex-col gap-1.5">
                {view.config.self_check.map((q, i) => (
                  <li key={q}>
                    <label className="flex cursor-pointer items-start gap-2 text-xs text-zinc-600 dark:text-zinc-400">
                      <input type="checkbox" className="mt-0.5" checked={checks[i] ?? false} onChange={() => setChecks((c) => c.map((v, j) => (j === i ? !v : v)))} />
                      {q}
                    </label>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {problems.length > 0 && (
            <Notice>
              <ul className="list-disc pl-4">
                {problems.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            </Notice>
          )}
          <Button variant="primary" disabled={!allDone || !checks.every(Boolean) || submitting || readOnly} onClick={() => void submit()}>
            Nộp job
          </Button>
          {!allDone && (
            <p className="-mt-3 text-xs text-zinc-500">
              Cần gán nhãn đủ {allTargets.length} tool call
              {view.config.label_schema.unsure_field ? "; chọn “Không chắc” cho bước bạn chưa chắc để reviewer chú ý." : "."}
            </p>
          )}
        </aside>
      </div>

      {showGuideline && (
        <Modal title={`Guideline v${view.guideline.version}`} onClose={() => setShowGuideline(false)}>
          <pre className="whitespace-pre-wrap font-sans text-sm">{view.guideline.content}</pre>
        </Modal>
      )}
      {done && (
        <Modal title="Đã nộp job" onClose={() => router.push("/work")}>
          <div className="flex flex-col gap-4">
            <Notice tone="green">Job đã nộp (lượt {done.round}). Reviewer sẽ chấm.</Notice>
            <div className="flex justify-end gap-2">
              <Button onClick={() => router.push("/")}>Về trang chủ</Button>
              <Button variant="primary" onClick={() => router.push("/work")}>
                Về hàng đợi
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
