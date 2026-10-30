"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { StepsView } from "@/components/step-view";
import { Badge, Button, Field, Modal, Notice, Select, Spinner, Textarea, Input, formatDate } from "@/components/ui";
import { ApiError, errorMessage, get, post } from "@/lib/api";
import type { JobView, ReviewErrorView, RoundView, Step } from "@/lib/types";

type Decision = "accept" | "accept_with_fix" | "reject" | "escalate";

const DECISION_LABEL: Record<Decision, string> = {
  accept: "Chấp nhận",
  accept_with_fix: "Chấp nhận (lỗi nhỏ)",
  reject: "Trả lại",
  escalate: "Escalate",
};

/** Suggested decision from the severity thresholds in review_workflow.md. */
function suggest(errors: ReviewErrorView[]): Decision {
  if (errors.some((e) => e.severity === "critical" || e.severity === "major")) return "reject";
  if (errors.length > 0) return "accept_with_fix";
  return "accept";
}

export default function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [view, setView] = useState<JobView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errors, setErrors] = useState<ReviewErrorView[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [roundIndex, setRoundIndex] = useState(0);
  const [adding, setAdding] = useState({ reason_code: "", severity: "major", note: "" });
  const [decision, setDecision] = useState<Decision | null>(null);
  const [reason, setReason] = useState("");
  const [problems, setProblems] = useState<string[]>([]);
  const [done, setDone] = useState<{ status: string } | null>(null);
  const [showGuideline, setShowGuideline] = useState(false);
  const [busy, setBusy] = useState(false);
  const { projects } = useAuth();
  const [override, setOverride] = useState<{ decision: "accept" | "reject"; reason: string }>({ decision: "reject", reason: "" });
  const [overrideDone, setOverrideDone] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        let v = await get<JobView>(`/jobs/${id}/review-context`);
        if (v.job.status === "submitted" && v.my_role === "reviewer") {
          await post(`/jobs/${id}/review/start`);
          v = await get<JobView>(`/jobs/${id}/review-context`);
        }
        setView(v);
        setRoundIndex(Math.max(0, (v.rounds?.length ?? 1) - 1));
        setSelected(v.items[0]?.payload.targets[0] ?? null);
      } catch (e) {
        setError(errorMessage(e));
      }
    })();
  }, [id]);

  const rounds = useMemo<RoundView[]>(() => view?.rounds ?? [], [view]);
  const round = rounds[roundIndex];
  const isCurrent = roundIndex === rounds.length - 1;
  const canDecide = view?.job.status === "in_review" && view.my_role === "reviewer" && isCurrent;
  const item = view?.items[0];
  const reviewCodes = (view?.reason_codes ?? []).filter((c) => c.applies_to !== "label");
  const suggestion = suggest(errors);
  const hasUnsure = round?.annotations.some((a) => a.is_unsure) ?? false;

  const labels = useMemo(() => {
    const map = new Map<string, RoundView["annotations"][number]>();
    for (const a of round?.annotations ?? []) map.set(`${a.item_id}:${a.target}`, a);
    return map;
  }, [round]);

  const marks = useMemo(() => {
    const map = new Map<string, ReviewErrorView[]>();
    const source = isCurrent ? errors : (round?.review?.errors ?? []);
    for (const e of source) map.set(`${e.item_id}:${e.target}`, [...(map.get(`${e.item_id}:${e.target}`) ?? []), e]);
    return map;
  }, [errors, round, isCurrent]);

  function addError() {
    if (!item || !selected || !adding.reason_code) return;
    setErrors((list) => [
      ...list,
      { item_id: item.id, target: selected, reason_code: adding.reason_code, severity: adding.severity, note: adding.note || null },
    ]);
    setAdding({ reason_code: "", severity: "major", note: "" });
  }

  async function submitOverride() {
    if (!view) return;
    setBusy(true);
    setProblems([]);
    try {
      const job = await post<{ status: string }>(`/projects/${view.job.project_id}/jobs/${id}/override`, override);
      setOverrideDone(job.status);
    } catch (e) {
      setProblems([errorMessage(e)]);
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    if (!decision) return;
    setBusy(true);
    setProblems([]);
    try {
      const result = await post<{ job_status: string }>(`/jobs/${id}/reviews`, {
        decision,
        reason: reason || null,
        errors,
      });
      setDone({ status: result.job_status });
    } catch (e) {
      const details = e instanceof ApiError ? (e.details as { errors?: string[] } | undefined) : undefined;
      setProblems(details?.errors ?? [errorMessage(e)]);
      setBusy(false);
    }
  }

  if (error) {
    return (
      <div className="mx-auto mt-20 flex max-w-md flex-col gap-4 px-4">
        <Notice>{error}</Notice>
        <Link href="/review" className="text-sm underline underline-offset-2">
          Về hàng đợi chấm
        </Link>
      </div>
    );
  }
  if (!view || !item) return <Spinner />;

  const steps = item.payload.steps as Step[];
  const label = selected ? labels.get(`${item.id}:${selected}`) : undefined;
  const selectedMarks = selected ? (marks.get(`${item.id}:${selected}`) ?? []) : [];

  return (
    <>
      <header className="flex flex-wrap items-center gap-x-5 gap-y-2 border-b border-zinc-200 px-5 py-3 dark:border-zinc-800">
        <Link href={view.my_role === "reviewer" ? "/review" : "/"} className="text-sm text-zinc-500 underline underline-offset-2">
          ← Thoát
        </Link>
        <div>
          <p className="text-xs text-zinc-500">{view.task.name}</p>
          <h1 className="text-base font-semibold">
            Chấm job #{view.job.ordinal} <Badge>{view.job.status}</Badge>
          </h1>
        </div>
        <button type="button" onClick={() => setShowGuideline(true)} className="rounded-full border border-zinc-200 px-2.5 py-0.5 text-xs text-zinc-600 hover:bg-zinc-100 dark:border-zinc-800 dark:text-zinc-400 dark:hover:bg-zinc-900">
          Guideline v{view.guideline.version}
        </button>
        {hasUnsure && <Badge tone="amber">có bước annotator không chắc</Badge>}
        {rounds.length > 1 && (
          <div className="ml-auto flex items-center gap-2 text-sm">
            <span className="text-zinc-500">Vòng:</span>
            {rounds.map((r, i) => (
              <Button key={r.round} variant={i === roundIndex ? "primary" : "secondary"} onClick={() => setRoundIndex(i)}>
                {r.round}
              </Button>
            ))}
          </div>
        )}
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[1fr_400px]">
        <section className="overflow-y-auto px-5 py-5">
          {round && (
            <p className="mb-3 text-xs text-zinc-500">
              Vòng {round.round} · nộp {formatDate(round.submitted_at)}
              {round.review && ` · quyết định: ${round.review.decision}${round.review.reason ? ` (${round.review.reason})` : ""}`}
            </p>
          )}
          <StepsView
            steps={steps}
            selectedId={selected}
            onSelect={setSelected}
            tone={(stepId) => {
              if (marks.has(`${item.id}:${stepId}`)) return "bad";
              const l = labels.get(`${item.id}:${stepId}`);
              return l?.is_unsure ? "warn" : null;
            }}
            decorate={(step) => {
              const l = labels.get(`${item.id}:${step.id}`);
              return (
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  {l && <Badge>{String(l.value.verdict ?? "đã gán nhãn")}</Badge>}
                  {marks.get(`${item.id}:${step.id}`)?.map((e, i) => (
                    <Badge key={i} tone="red">
                      {e.reason_code}
                    </Badge>
                  ))}
                </div>
              );
            }}
          />
        </section>

        <aside className="flex min-h-0 flex-col gap-5 overflow-y-auto border-t border-zinc-200 p-5 dark:border-zinc-800 lg:border-t-0 lg:border-l">
          {selected && (
            <div className="flex flex-col gap-3">
              <p className="font-mono text-sm font-semibold">{(steps.find((s) => s.id === selected) as { tool?: string })?.tool}</p>
              <div className="rounded-md border border-zinc-200 p-3 text-sm dark:border-zinc-800">
                <p className="mb-1 text-xs font-medium uppercase tracking-wide text-zinc-500">Nhãn của annotator</p>
                {label ? (
                  <>
                    <pre className="whitespace-pre-wrap font-mono text-xs">{JSON.stringify(label.value, null, 2)}</pre>
                    {label.is_unsure && <p className="mt-1 text-xs text-amber-600">Annotator đánh dấu không chắc.</p>}
                  </>
                ) : (
                  <p className="text-zinc-500">Không có nhãn.</p>
                )}
              </div>
              {selectedMarks.length > 0 && (
                <ul className="text-xs text-red-600">
                  {selectedMarks.map((e, i) => (
                    <li key={i}>
                      {e.reason_code} ({e.severity}) {e.note}
                    </li>
                  ))}
                </ul>
              )}
              {canDecide && (
                <div className="flex flex-col gap-2 rounded-md border border-dashed border-zinc-300 p-3 dark:border-zinc-700">
                  <p className="text-sm font-medium">Ghi lỗi ở bước này</p>
                  <Select value={adding.reason_code} onChange={(e) => setAdding({ ...adding, reason_code: e.target.value })}>
                    <option value="">— mã lỗi —</option>
                    {reviewCodes.map((c) => (
                      <option key={c.code} value={c.code}>
                        {c.code}: {c.label}
                      </option>
                    ))}
                  </Select>
                  <Select value={adding.severity} onChange={(e) => setAdding({ ...adding, severity: e.target.value })}>
                    <option value="critical">critical</option>
                    <option value="major">major</option>
                    <option value="minor">minor</option>
                  </Select>
                  <Input placeholder="Ghi chú ngắn" value={adding.note} onChange={(e) => setAdding({ ...adding, note: e.target.value })} />
                  <Button disabled={!adding.reason_code} onClick={addError}>
                    Thêm lỗi
                  </Button>
                </div>
              )}
            </div>
          )}

          <hr className="border-zinc-200 dark:border-zinc-800" />

          {canDecide ? (
            <>
              <div>
                <p className="mb-2 text-sm font-medium">Lỗi đã ghi ({errors.length})</p>
                {errors.length === 0 ? (
                  <p className="text-xs text-zinc-500">Chưa có lỗi nào.</p>
                ) : (
                  <ul className="flex flex-col gap-1 text-xs">
                    {errors.map((e, i) => (
                      <li key={i} className="flex items-center justify-between gap-2">
                        <span>
                          {e.target}: {e.reason_code} ({e.severity})
                        </span>
                        <button type="button" className="text-red-600 underline" onClick={() => setErrors((l) => l.filter((_, j) => j !== i))}>
                          xoá
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                <p className="mt-2 text-xs text-zinc-500">
                  Gợi ý theo ngưỡng: <strong>{DECISION_LABEL[suggestion]}</strong>. Không lỗi: chấp nhận; chỉ lỗi nhỏ: chấp nhận kèm ghi nhận; có lỗi lớn: trả lại.
                </p>
              </div>
              <Field label="Quyết định">
                <Select value={decision ?? ""} onChange={(e) => setDecision((e.target.value || null) as Decision | null)}>
                  <option value="">— chọn —</option>
                  {(Object.keys(DECISION_LABEL) as Decision[]).map((d) => (
                    <option key={d} value={d}>
                      {DECISION_LABEL[d]}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label={decision === "reject" || decision === "escalate" ? "Lý do (bắt buộc)" : "Ghi chú (tuỳ chọn)"} hint={decision === "reject" ? "1–3 câu chỉ rõ cần sửa gì; đừng viết “làm lại đi”." : undefined}>
                <Textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
              </Field>
              {problems.length > 0 && (
                <Notice>
                  <ul className="list-disc pl-4">
                    {problems.map((p) => (
                      <li key={p}>{p}</li>
                    ))}
                  </ul>
                </Notice>
              )}
              <Button
                variant="primary"
                disabled={!decision || busy || ((decision === "reject" || decision === "escalate") && reason.trim().length < 3)}
                onClick={() => void submit()}
              >
                Lưu quyết định
              </Button>
              <p className="text-xs text-zinc-500">Quyết định không sửa được sau khi lưu. Không chắc vì guideline mơ hồ thì chọn Escalate.</p>
            </>
          ) : (
            <>
              <Notice tone="blue">
                {view.my_role === "reviewer"
                  ? "Đây là vòng đã chấm; chỉ xem."
                  : "Bạn đang xem chỉ đọc."}
              </Notice>
              {view.my_role === "coordinator" &&
                projects.find((p) => p.id === view.job.project_id)?.my_permissions.includes("review.override") &&
                ["accepted", "accepted_with_fix", "rejected"].includes(view.job.status) &&
                (overrideDone ? (
                  <Notice tone="green">Đã đổi quyết định; job giờ ở trạng thái “{overrideDone}”.</Notice>
                ) : (
                  <div className="flex flex-col gap-3 rounded-md border border-dashed border-zinc-300 p-3 dark:border-zinc-700">
                    <p className="text-sm font-medium">Đổi quyết định của reviewer (owner)</p>
                    <p className="text-xs text-zinc-500">Tạo bản ghi mới, bản cũ được giữ. Bắt buộc có lý do và được ghi audit.</p>
                    <Select value={override.decision} onChange={(e) => setOverride({ ...override, decision: e.target.value as "accept" | "reject" })}>
                      <option value="accept">Chấp nhận job</option>
                      <option value="reject">Trả lại cho annotator</option>
                    </Select>
                    <Textarea rows={3} placeholder="Lý do" value={override.reason} onChange={(e) => setOverride({ ...override, reason: e.target.value })} />
                    {problems.length > 0 && <Notice>{problems.join("; ")}</Notice>}
                    <Button variant="danger" disabled={busy || override.reason.trim().length < 3} onClick={() => void submitOverride()}>
                      Đổi quyết định
                    </Button>
                  </div>
                ))}
            </>
          )}
        </aside>
      </div>

      {showGuideline && (
        <Modal title={`Guideline v${view.guideline.version}`} onClose={() => setShowGuideline(false)}>
          <pre className="whitespace-pre-wrap font-sans text-sm">{view.guideline.content}</pre>
        </Modal>
      )}
      {done && (
        <Modal title="Đã lưu quyết định" onClose={() => router.push("/review")}>
          <div className="flex flex-col gap-4">
            <Notice tone="green">Job chuyển sang trạng thái “{done.status}”.</Notice>
            <div className="flex justify-end gap-2">
              <Button onClick={() => router.push("/")}>Về trang chủ</Button>
              <Button variant="primary" onClick={() => router.push("/review")}>
                Về hàng đợi chấm
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
