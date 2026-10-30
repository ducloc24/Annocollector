"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Badge, Button, Card, Empty, formatDate, Loaded, Notice, PageHeader, useAsync } from "@/components/ui";
import { ApiError, errorMessage, get, post } from "@/lib/api";
import type { JobView, Queue } from "@/lib/types";

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

export function WorkerQueue({ mode }: { mode: Mode }) {
  const c = copy[mode];
  const router = useRouter();
  const queues = useAsync(() => get<Queue[]>("/me/queues"));
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

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
    </>
  );
}
