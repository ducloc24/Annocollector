"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Badge, Button, Card, Empty, Field, formatDate, Loaded, Modal, Notice, PageHeader, Table, Td, Textarea, useAsync } from "@/components/ui";
import { ApiError, errorMessage, get, post } from "@/lib/api";
import type { Appeal, Job, JobView, Queue } from "@/lib/types";

type Mode = "annotate" | "review";

const copy = {
  annotate: {
    title: "Gán nhãn",
    subtitle: "Lấy việc tiếp theo; hệ thống chọn job cho bạn.",
    role: "annotator",
    next: (id: string) => `/projects/${id}/jobs/next`,
    open: (id: string) => `/jobs/${id}/annotate`,
    button: "Lấy việc tiếp theo",
  },
  review: {
    title: "Chấm",
    subtitle: "Lấy job cần chấm tiếp theo.",
    role: "reviewer",
    next: (id: string) => `/projects/${id}/reviews/next`,
    open: (id: string) => `/jobs/${id}/review`,
    button: "Lấy việc chấm",
  },
} as const;

function AppealDialog({ job, onClose, onDone }: { job: Job; onClose: () => void; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  async function submit() {
    try {
      await post(`/jobs/${job.id}/appeals`, { reason });
      onDone();
      onClose();
    } catch (e) {
      setError(
        e instanceof ApiError && e.code === "appeal_window_closed"
          ? "Đã quá hạn khiếu nại."
          : errorMessage(e),
      );
    }
  }
  return (
    <Modal title={`Khiếu nại job #${job.ordinal}`} onClose={onClose}>
      <div className="flex flex-col gap-3">
        {error && <Notice>{error}</Notice>}
        <p className="text-sm text-zinc-500">
          Nêu lý do bạn cho rằng quyết định trả lại là sai. PM xem trước, có thể chuyển lên owner. Căn cứ là guideline đã ghim lúc bạn làm.
        </p>
        <Field label="Lý do">
          <Textarea rows={4} value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Huỷ</Button>
          <Button variant="primary" disabled={reason.trim().length < 3} onClick={() => void submit()}>
            Gửi khiếu nại
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function MyAppeals({ refreshKey }: { refreshKey: number }) {
  const state = useAsync(() => get<Appeal[]>("/me/appeals"), [refreshKey]);
  return (
    <Loaded state={state}>
      {(rows) =>
        rows.length === 0 ? null : (
          <Card title="Khiếu nại của tôi" className="mt-6">
            <Table head={["Job", "Lý do", "Trạng thái", "Kết quả", "Mở lúc"]}>
              {rows.map((a) => (
                <tr key={a.id}>
                  <Td>#{a.job_ordinal}</Td>
                  <Td className="max-w-xs truncate">{a.reason}</Td>
                  <Td>{a.status === "closed" ? "Đã đóng" : "Đang xử lý"}</Td>
                  <Td>{a.outcome === "overturned" ? "Được chấp nhận" : a.outcome === "upheld" ? "Giữ nguyên quyết định" : "—"}{a.resolution ? `: ${a.resolution}` : ""}</Td>
                  <Td>{formatDate(a.opened_at)}</Td>
                </tr>
              ))}
            </Table>
          </Card>
        )
      }
    </Loaded>
  );
}

export function WorkerQueue({ mode }: { mode: Mode }) {
  const c = copy[mode];
  const router = useRouter();
  const queues = useAsync(() => get<Queue[]>("/me/queues"));
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [appealing, setAppealing] = useState<Job | null>(null);
  const [appealKey, setAppealKey] = useState(0);

  async function pull(projectId: string) {
    setBusy(projectId);
    setMessage(null);
    try {
      const view = await post<JobView | undefined>(c.next(projectId));
      if (!view) {
        setMessage("Hiện không còn việc cho bạn trong project này.");
        setBusy(null);
        return;
      }
      router.push(c.open(view.job.id));
    } catch (e) {
      setMessage(
        e instanceof ApiError && e.code === "wip_limit_reached"
          ? "Bạn đang giữ đủ số job tối đa. Hoàn thành bớt rồi lấy tiếp."
          : errorMessage(e),
      );
      setBusy(null);
    }
  }

  return (
    <>
      <PageHeader title={c.title} subtitle={c.subtitle} />
      {message && (
        <div className="mb-4">
          <Notice tone="amber">{message}</Notice>
        </div>
      )}
      <Loaded state={queues}>
        {(all) => {
          const mine = all.filter((q) => q.roles.includes(c.role));
          if (mine.length === 0) return <Empty>Bạn chưa được giao việc ở project nào.</Empty>;
          return (
            <div className="flex flex-col gap-5">
              {mine.map((q) => {
                const jobs = mode === "annotate" ? q.my_jobs : q.my_reviews;
                return (
                  <Card
                    key={q.project.id}
                    title={
                      <>
                        {q.project.name} <Badge>{q.project.status}</Badge>
                      </>
                    }
                    actions={
                      <Button
                        variant="primary"
                        disabled={!q.active || busy === q.project.id}
                        onClick={() => void pull(q.project.id)}
                      >
                        {c.button}
                      </Button>
                    }
                  >
                    {!q.active && <Notice tone="amber">Project chưa hoạt động nên chưa lấy được việc.</Notice>}
                    {mode === "review" && (
                      <p className="mb-3 text-sm text-zinc-500">{q.waiting_for_review} job đang chờ chấm.</p>
                    )}
                    {jobs.length === 0 ? (
                      <Empty>{mode === "annotate" ? "Bạn chưa có job đang làm." : "Bạn chưa có job đang chấm."}</Empty>
                    ) : (
                      <ul className="divide-y divide-zinc-100 dark:divide-zinc-900">
                        {jobs.map((j) => (
                          <li key={j.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                            <div>
                              <Link href={c.open(j.id)} className="font-medium underline-offset-2 hover:underline">
                                Job #{j.ordinal}
                              </Link>{" "}
                              <Badge>{j.status}</Badge>
                              {j.status === "rejected" && (
                                <span className="ml-2 text-red-600">bị trả lại, còn lượt sửa</span>
                              )}
                              {mode === "annotate" && j.status === "rejected" && (
                                <Button variant="ghost" onClick={() => setAppealing(j)}>
                                  Khiếu nại
                                </Button>
                              )}
                            </div>
                            <span className="text-xs text-zinc-500">
                              {j.lease_expires_at ? `hạn giữ ${formatDate(j.lease_expires_at)}` : ""}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </Card>
                );
              })}
            </div>
          );
        }}
      </Loaded>
      {mode === "annotate" && <MyAppeals refreshKey={appealKey} />}
      {appealing && (
        <AppealDialog
          job={appealing}
          onClose={() => setAppealing(null)}
          onDone={() => {
            setAppealKey((k) => k + 1);
            void queues.reload();
          }}
        />
      )}
    </>
  );
}
