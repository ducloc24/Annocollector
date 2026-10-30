"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { useAuth } from "@/components/auth-provider";
import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  Empty,
  formatDate,
  Loaded,
  Notice,
  PageHeader,
  Table,
  Td,
  useAsync,
} from "@/components/ui";
import { download, errorMessage, get, post } from "@/lib/api";
import type { Acceptance, Job, Page, Progress, Project, Task } from "@/lib/types";

const LABELS: Record<string, string> = {
  unassigned: "Chưa giao",
  assigned: "Đã giao",
  in_progress: "Đang làm",
  submitted: "Chờ chấm",
  in_review: "Đang chấm",
  rejected: "Bị trả lại",
  escalated: "Escalate",
  accepted: "Đạt",
  accepted_with_fix: "Đạt (sửa nhỏ)",
};

export default function TaskPage() {
  const { id, tid } = useParams<{ id: string; tid: string }>();
  const { projects } = useAuth();
  const project: Project | undefined = projects.find((p) => p.id === id);
  const canAccept = project?.my_permissions.includes("task.accept") ?? false;
  const task = useAsync(() => get<Task>(`/projects/${id}/tasks/${tid}`), [id, tid]);
  const progress = useAsync(() => get<Progress>(`/projects/${id}/progress?task_id=${tid}`), [id, tid]);
  const acceptance = useAsync(
    () => (canAccept ? get<Acceptance>(`/projects/${id}/tasks/${tid}/acceptance`) : Promise.resolve(null)),
    [id, tid, canAccept],
  );
  const jobs = useAsync(() => get<Page<Job>>(`/projects/${id}/jobs?task_id=${tid}&limit=100`), [id, tid]);
  const [signing, setSigning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gold, setGold] = useState<Job | null>(null);
  const canAssign = project?.my_permissions.includes("job.assign") ?? false;
  const canExport = project?.my_permissions.includes("export.data") ?? false;
  const canOverride = project?.my_permissions.includes("review.override") ?? false;

  async function refresh() {
    await Promise.all([task.reload(), progress.reload(), acceptance.reload()]);
  }

  return (
    <Loaded state={task}>
      {(t) => (
        <>
          <PageHeader
            title={
              <>
                {t.name} <Badge>{t.status}</Badge>
              </>
            }
            subtitle={`${t.jobs_total} job · tạo ${formatDate(t.created_at)}${t.delivered_at ? ` · đã giao ${formatDate(t.delivered_at)}` : ""}`}
            actions={
              <>
                {t.status === "delivered" && canExport && (
                  <Button
                    onClick={async () => {
                      try {
                        await download(`/projects/${id}/tasks/${tid}/export`, `${t.name}.jsonl`);
                      } catch (e) {
                        setError(errorMessage(e));
                      }
                    }}
                  >
                    Export JSONL
                  </Button>
                )}
                <Link href={`/projects/${id}?tab=tasks`} className="text-sm underline underline-offset-2">
                  ← Task
                </Link>
              </>
            }
          />
          {error && <div className="mb-4"><Notice>{error}</Notice></div>}
          <div className="flex flex-col gap-6">
            <Loaded state={progress}>
              {(p) => (
                <Card title="Tiến độ task">
                  <p className="mb-3 text-sm">
                    <strong>{Math.round(p.completion_rate * 100)}%</strong> hoàn thành · backlog {p.backlog} · tỷ lệ đạt ngay lần đầu{" "}
                    {p.first_pass_rate === null ? "—" : `${Math.round(p.first_pass_rate * 100)}%`}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(p.by_status)
                      .filter(([, n]) => n > 0)
                      .map(([s, n]) => (
                        <Badge key={s}>
                          {LABELS[s] ?? s}: {n}
                        </Badge>
                      ))}
                  </div>
                </Card>
              )}
            </Loaded>

            {canAccept && (
              <Loaded state={acceptance}>
                {(a) =>
                  a && (
                    <Card
                      title="Nghiệm thu"
                      actions={
                        t.status === "active" && (
                          <Button variant="primary" disabled={!a.can_sign_off} onClick={() => setSigning(true)}>
                            Ký nghiệm thu
                          </Button>
                        )
                      }
                    >
                      {t.status === "delivered" ? (
                        <Notice tone="green">Task đã được nghiệm thu và giao.</Notice>
                      ) : a.can_sign_off ? (
                        <Notice tone="green">Mọi job đã kết thúc. Xem mẫu bên dưới rồi ký nghiệm thu.</Notice>
                      ) : (
                        <Notice tone="amber">Còn {a.open_jobs} job chưa kết thúc nên chưa ký nghiệm thu được.</Notice>
                      )}
                      {a.sample_job_ids.length > 0 && (
                        <div className="mt-4">
                          <p className="mb-2 text-sm font-medium">Mẫu ngẫu nhiên để kiểm chứng chất lượng reviewer</p>
                          <div className="flex flex-wrap gap-2">
                            {a.sample_job_ids.map((jobId) => {
                              const job = jobs.data?.items.find((j) => j.id === jobId);
                              return (
                                <Link key={jobId} href={`/jobs/${jobId}/review`} className="rounded-md border border-zinc-300 px-2 py-1 text-sm hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-900">
                                  Job #{job?.ordinal ?? jobId.slice(0, 6)}
                                </Link>
                              );
                            })}
                          </div>
                        </div>
                      )}
                    </Card>
                  )
                }
              </Loaded>
            )}

            <Card title="Danh sách job">
              <Loaded state={jobs}>
                {(page) =>
                  page.items.length === 0 ? (
                    <Empty>Chưa có job.</Empty>
                  ) : (
                    <Table head={["Job", "Trạng thái", "Sửa", "Nộp lúc", "Đóng lúc", ""]}>
                      {page.items.map((j) => (
                        <tr key={j.id}>
                          <Td>#{j.ordinal}</Td>
                          <Td>
                            <Badge>{j.status}</Badge>
                          </Td>
                          <Td>{j.rework_count}</Td>
                          <Td>{formatDate(j.submitted_at)}</Td>
                          <Td>{formatDate(j.closed_at)}</Td>
                          <Td className="text-right">
                            <div className="flex justify-end gap-2">
                              {["accepted", "accepted_with_fix", "rejected"].includes(j.status) && (
                                <Link href={`/jobs/${j.id}/review`} className="text-sm underline underline-offset-2">
                                  {canOverride ? "Xem / đổi quyết định" : "Xem"}
                                </Link>
                              )}
                              {canAssign && ["accepted", "accepted_with_fix"].includes(j.status) && (
                                <Button variant="ghost" onClick={() => setGold(j)}>
                                  Làm gold job
                                </Button>
                              )}
                            </div>
                          </Td>
                        </tr>
                      ))}
                    </Table>
                  )
                }
              </Loaded>
            </Card>
          </div>
          {gold && (
            <ConfirmDialog
              title={`Tạo gold job từ job #${gold.ordinal}`}
              message="Hệ thống nhân bản job này thành một job mới trong hàng đợi; nhãn đã được chấp nhận của job gốc là đáp án chuẩn. Người làm không biết đó là gold job. Dùng để đo độ chính xác của annotator."
              confirmLabel="Tạo gold job"
              onClose={() => setGold(null)}
              onConfirm={async () => {
                await post(`/projects/${id}/gold-jobs`, { job_id: gold.id });
                await jobs.reload();
              }}
            />
          )}
          {signing && (
            <ConfirmDialog
              title="Ký nghiệm thu task"
              message="Task chuyển sang trạng thái đã giao. Không đảo ngược được."
              confirmLabel="Ký nghiệm thu"
              onClose={() => setSigning(false)}
              onConfirm={async () => {
                try {
                  await post(`/projects/${id}/tasks/${tid}/sign-off`);
                  await refresh();
                } catch (e) {
                  setError(errorMessage(e));
                  throw e;
                }
              }}
            />
          )}
        </>
      )}
    </Loaded>
  );
}
