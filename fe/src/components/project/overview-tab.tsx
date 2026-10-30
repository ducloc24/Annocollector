"use client";

import Link from "next/link";
import { useState } from "react";

import { Badge, Button, Card, ConfirmDialog, Loaded, Notice, useAsync } from "@/components/ui";
import { errorMessage, get, post } from "@/lib/api";
import type { Dataset, Guideline, JobConfig, Progress, Project, ProjectTeam, Task } from "@/lib/types";

const STATUS_LABEL: Record<string, string> = {
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

function Checklist({ project }: { project: Project }) {
  const owner = project.my_roles.includes("owner");
  const state = useAsync(async () => {
    const [guidelines, teams, datasets, configs, tasks] = await Promise.all([
      get<Guideline[]>(`/projects/${project.id}/guidelines`),
      get<ProjectTeam[]>(`/projects/${project.id}/teams`),
      get<Dataset[]>(`/projects/${project.id}/datasets`),
      get<JobConfig[]>(`/projects/${project.id}/job-configs`),
      get<Task[]>(`/projects/${project.id}/tasks`),
    ]);
    return { guidelines, teams, datasets, configs, tasks };
  }, [project.id, project.status]);

  if (!owner) return null;
  return (
    <Loaded state={state}>
      {({ guidelines, teams, datasets, configs, tasks }) => {
        const steps = [
          { tab: "guideline", label: "Viết guideline", done: guidelines.length > 0 },
          { tab: "people", label: "Gắn đội đánh giá (đủ annotator và reviewer)", done: teams.length > 0 },
          { tab: "data", label: "Upload dữ liệu và tạo dataset version", done: datasets.length > 0 },
          { tab: "config", label: "Cấu hình job (label schema, quy tắc)", done: configs.length > 0 },
          { tab: "tasks", label: "Tạo task và giao cho đội", done: tasks.length > 0 },
          { tab: "overview", label: "Kích hoạt project", done: project.status === "active" },
          { tab: "tasks", label: "Kích hoạt task", done: tasks.some((t) => t.status !== "draft") },
        ];
        if (steps.every((s) => s.done)) return null;
        return (
          <Card title="Checklist thiết lập" className="mb-6">
            <ol className="flex flex-col gap-2 text-sm">
              {steps.map((s, i) => (
                <li key={i} className="flex items-center gap-2">
                  <span className={s.done ? "text-emerald-600" : "text-zinc-400"}>{s.done ? "✓" : "○"}</span>
                  {s.done ? (
                    <span className="text-zinc-500 line-through">{s.label}</span>
                  ) : (
                    <Link href={`/projects/${project.id}?tab=${s.tab}`} className="underline underline-offset-2">
                      {s.label}
                    </Link>
                  )}
                </li>
              ))}
            </ol>
          </Card>
        );
      }}
    </Loaded>
  );
}

export function OverviewTab({ project, onChange }: { project: Project; onChange: () => Promise<void> }) {
  const canUpdate = project.my_permissions.includes("project.update");
  const canProgress = project.my_permissions.includes("progress.read");
  const progress = useAsync(
    () => (canProgress ? get<Progress>(`/projects/${project.id}/progress`) : Promise.resolve(null)),
    [project.id, project.status],
  );
  const [action, setAction] = useState<"activate" | "pause" | "close" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(next: "activate" | "pause" | "close") {
    setError(null);
    try {
      await post(`/projects/${project.id}/${next}`);
      await onChange();
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  return (
    <>
      <Checklist project={project} />
      {error && <div className="mb-4"><Notice>{error}</Notice></div>}
      {canUpdate && project.status !== "closed" && (
        <Card
          title="Trạng thái project"
          className="mb-6"
          actions={
            <>
              {(project.status === "draft" || project.status === "paused") && (
                <Button variant="primary" onClick={() => void run("activate")}>
                  Kích hoạt
                </Button>
              )}
              {project.status === "active" && <Button onClick={() => void run("pause")}>Tạm dừng</Button>}
              <Button variant="danger" onClick={() => setAction("close")}>
                Đóng project
              </Button>
            </>
          }
        >
          <p className="text-sm text-zinc-500">
            {project.status === "draft" && "Project đang nháp: hoàn tất checklist rồi kích hoạt để annotator và reviewer bắt đầu."}
            {project.status === "active" && "Project đang chạy. Tạm dừng để ngừng giao việc mới; job đang làm vẫn giữ."}
            {project.status === "paused" && "Project tạm dừng, chưa ai lấy được việc mới."}
          </p>
        </Card>
      )}
      {project.description && (
        <Card title="Mô tả" className="mb-6">
          <p className="whitespace-pre-wrap text-sm">{project.description}</p>
        </Card>
      )}
      {canProgress && (
        <Loaded state={progress}>
          {(p) =>
            p && (
              <Card title="Tiến độ">
                <div className="mb-4 grid gap-4 sm:grid-cols-4">
                  <div>
                    <p className="text-2xl font-semibold">{Math.round(p.completion_rate * 100)}%</p>
                    <p className="text-sm text-zinc-500">hoàn thành ({p.jobs_total} job)</p>
                  </div>
                  <div>
                    <p className="text-2xl font-semibold">{p.backlog}</p>
                    <p className="text-sm text-zinc-500">backlog</p>
                  </div>
                  <div>
                    <p className="text-2xl font-semibold">{p.throughput_per_day}</p>
                    <p className="text-sm text-zinc-500">job đạt / ngày (7 ngày)</p>
                  </div>
                  <div>
                    <p className="text-2xl font-semibold">{p.cycle_time_hours.p50 ?? "—"}</p>
                    <p className="text-sm text-zinc-500">giờ giao → đạt (trung vị)</p>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(p.by_status)
                    .filter(([, n]) => n > 0)
                    .map(([status, n]) => (
                      <Badge key={status}>
                        {STATUS_LABEL[status] ?? status}: {n}
                      </Badge>
                    ))}
                  {p.stuck > 0 && <Badge tone="amber">{p.stuck} job kẹt quá 24 giờ</Badge>}
                </div>
                <p className="mt-3 text-xs text-zinc-500">
                  Chỉ job đã được chấp nhận mới tính vào % hoàn thành.
                </p>
              </Card>
            )
          }
        </Loaded>
      )}
      {action === "close" && (
        <ConfirmDialog
          title="Đóng project"
          message="Project đóng chỉ còn đọc, không mở lại được."
          danger
          confirmLabel="Đóng"
          onClose={() => setAction(null)}
          onConfirm={async () => {
            await post(`/projects/${project.id}/close`);
            await onChange();
          }}
        />
      )}
    </>
  );
}
