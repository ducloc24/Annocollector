"use client";

import Link from "next/link";

import { useAuth } from "@/components/auth-provider";
import { Badge, Card, Empty, Loaded, PageHeader, useAsync } from "@/components/ui";
import { get } from "@/lib/api";
import type { Progress, Queue } from "@/lib/types";

function Stat({ label, value, href }: { label: string; value: number | string; href: string }) {
  return (
    <Link
      href={href}
      className="rounded-lg border border-zinc-200 p-4 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-950"
    >
      <p className="text-2xl font-semibold">{value}</p>
      <p className="text-sm text-zinc-500">{label}</p>
    </Link>
  );
}

function WorkerCards({ queues }: { queues: Queue[] }) {
  if (queues.length === 0) return null;
  return (
    <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {queues.flatMap((q) => [
        q.roles.includes("annotator") && (
          <Stat
            key={`${q.project.id}-a`}
            href="/work"
            value={q.my_jobs.length}
            label={`${q.project.name}: job của tôi${q.my_jobs.some((j) => j.status === "rejected") ? " (có job bị trả lại)" : ""}`}
          />
        ),
        q.roles.includes("reviewer") && (
          <Stat
            key={`${q.project.id}-r`}
            href="/review"
            value={q.waiting_for_review}
            label={`${q.project.name}: job chờ chấm`}
          />
        ),
      ])}
    </div>
  );
}

function ManagerCards() {
  const { projects } = useAuth();
  const managed = projects.filter(
    (p) => p.status !== "closed" && p.my_permissions.includes("progress.read") && p.my_roles.some((r) => r === "owner" || r === "manager"),
  );
  const state = useAsync(async () => {
    return Promise.all(
      managed.map(async (p) => ({
        project: p,
        progress: await get<Progress>(`/projects/${p.id}/progress`),
      })),
    );
  }, [managed.map((p) => p.id).join(",")]);

  if (managed.length === 0) return null;
  return (
    <Card title="Project của tôi" className="mb-8">
      <Loaded state={state}>
        {(rows) => (
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-900">
            {rows.map(({ project, progress }) => (
              <li key={project.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div>
                  <Link href={`/projects/${project.id}`} className="font-medium underline-offset-2 hover:underline">
                    {project.name}
                  </Link>{" "}
                  <Badge>{project.status}</Badge>
                  <p className="text-sm text-zinc-500">
                    {Math.round(progress.completion_rate * 100)}% hoàn thành · {progress.jobs_total} job · backlog {progress.backlog}
                  </p>
                </div>
                <div className="flex gap-2 text-sm">
                  {progress.by_status.escalated > 0 && (
                    <Link href={`/projects/${project.id}?tab=escalations`}>
                      <Badge tone="red">{progress.by_status.escalated} escalation</Badge>
                    </Link>
                  )}
                  {progress.stuck > 0 && (
                    <Link href={`/projects/${project.id}?tab=jobs&stuck=1`}>
                      <Badge tone="amber">{progress.stuck} job kẹt</Badge>
                    </Link>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Loaded>
    </Card>
  );
}

export default function HomePage() {
  const { user, can, teams, projects } = useAuth();
  const queues = useAsync(() => get<Queue[]>("/me/queues"));
  const draftProjects = projects.filter((p) => p.status === "draft" && p.my_roles.includes("owner"));
  const hasWork = teams.length > 0;

  return (
    <>
      <PageHeader title={`Xin chào, ${user?.full_name}`} subtitle="Việc cần làm hôm nay" />
      {hasWork && <Loaded state={queues}>{(q) => <WorkerCards queues={q} />}</Loaded>}
      <ManagerCards />
      {draftProjects.length > 0 && (
        <Card title="Thiết lập dở" className="mb-8">
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-900">
            {draftProjects.map((p) => (
              <li key={p.id} className="py-2">
                <Link href={`/projects/${p.id}`} className="underline underline-offset-2">
                  {p.name}
                </Link>{" "}
                <span className="text-sm text-zinc-500">còn ở trạng thái nháp</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
      {can("platform_role.grant") && (
        <Card title="Nhân sự">
          <Link href="/admin/roles/expiring" className="text-sm underline underline-offset-2">
            Xem quyền sắp hết hạn
          </Link>
        </Card>
      )}
      {!hasWork && projects.length === 0 && !can("user.manage") && !can("project.create") && (
        <Empty>Bạn chưa thuộc đội hay project nào. Liên hệ HR hoặc PO để được thêm vào.</Empty>
      )}
    </>
  );
}
