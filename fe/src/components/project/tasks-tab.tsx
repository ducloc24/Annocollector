"use client";

import Link from "next/link";
import { type FormEvent, useState } from "react";

import {
  Badge,
  Button,
  Card,
  Empty,
  Field,
  formatDate,
  Input,
  Loaded,
  Modal,
  Notice,
  Select,
  Table,
  Td,
  useAsync,
} from "@/components/ui";
import { ApiError, errorMessage, get, post } from "@/lib/api";
import type { Dataset, Guideline, JobConfig, Project, ProjectTeam, Task } from "@/lib/types";

function pct(task: Task): string {
  const done = (task.by_status.accepted ?? 0) + (task.by_status.accepted_with_fix ?? 0);
  return task.jobs_total ? `${Math.round((done / task.jobs_total) * 100)}% (${done}/${task.jobs_total})` : "—";
}

function CreateTask({ project, onClose, onDone }: { project: Project; onClose: () => void; onDone: () => void }) {
  const refs = useAsync(async () => {
    const [datasets, configs, guidelines, teams] = await Promise.all([
      get<Dataset[]>(`/projects/${project.id}/datasets`),
      get<JobConfig[]>(`/projects/${project.id}/job-configs`),
      get<Guideline[]>(`/projects/${project.id}/guidelines`),
      get<ProjectTeam[]>(`/projects/${project.id}/teams`),
    ]);
    return { datasets, configs, guidelines, teams };
  }, [project.id]);
  const [form, setForm] = useState({ name: "", dataset: "", config: "", guideline: "", team: "", priority: "0" });
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ jobs: number } | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const created = await post<{ jobs: number }>(`/projects/${project.id}/tasks`, {
        name: form.name,
        dataset_version: Number(form.dataset),
        job_config_version: Number(form.config),
        guideline_version: Number(form.guideline),
        team_id: form.team || null,
        priority: Number(form.priority),
      });
      setResult(created);
      onDone();
    } catch (err) {
      setError(
        err instanceof ApiError && err.code === "item_type_mismatch"
          ? "Dataset và cấu hình job thuộc hai loại item khác nhau."
          : errorMessage(err),
      );
    }
  }

  if (result) {
    return (
      <Modal title="Đã tạo task" onClose={onClose}>
        <div className="flex flex-col gap-3">
          <Notice tone="green">
            Hệ thống đã cắt thành {result.jobs} job (đang ở trạng thái nháp). Kích hoạt task để thành viên đội bắt đầu
            lấy việc.
          </Notice>
          <div className="flex justify-end">
            <Button variant="primary" onClick={onClose}>
              Xong
            </Button>
          </div>
        </div>
      </Modal>
    );
  }

  return (
    <Modal title="Tạo task" onClose={onClose}>
      <Loaded state={refs}>
        {({ datasets, configs, guidelines, teams }) => (
          <form onSubmit={submit} className="flex flex-col gap-3">
            {error && <Notice>{error}</Notice>}
            <Field label="Tên task">
              <Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </Field>
            <Field label="Dataset version">
              <Select required value={form.dataset} onChange={(e) => setForm({ ...form, dataset: e.target.value })}>
                <option value="">— chọn —</option>
                {datasets.map((d) => (
                  <option key={d.id} value={d.version}>
                    v{d.version} · {d.item_count} item · {d.item_type}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Cấu hình job">
              <Select required value={form.config} onChange={(e) => setForm({ ...form, config: e.target.value })}>
                <option value="">— chọn —</option>
                {configs.map((c) => (
                  <option key={c.id} value={c.version}>
                    v{c.version} · {c.item_type} · {c.job_rules.items_per_job} item/job
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Guideline">
              <Select required value={form.guideline} onChange={(e) => setForm({ ...form, guideline: e.target.value })}>
                <option value="">— chọn —</option>
                {guidelines.map((g) => (
                  <option key={g.id} value={g.version}>
                    v{g.version}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Đội thực hiện" hint="Có thể giao sau">
              <Select value={form.team} onChange={(e) => setForm({ ...form, team: e.target.value })}>
                <option value="">— chưa giao —</option>
                {teams.map((t) => (
                  <option key={t.id} value={t.team_id}>
                    {t.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Độ ưu tiên" hint="Số lớn hơn được làm trước">
              <Input type="number" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })} />
            </Field>
            <div className="flex justify-end gap-2">
              <Button onClick={onClose}>Huỷ</Button>
              <Button type="submit" variant="primary">
                Tạo và cắt job
              </Button>
            </div>
          </form>
        )}
      </Loaded>
    </Modal>
  );
}

export function TasksTab({ project }: { project: Project }) {
  const canManage = project.my_permissions.includes("task.manage");
  const state = useAsync(() => get<Task[]>(`/projects/${project.id}/tasks`), [project.id]);
  const teams = useAsync(() => get<ProjectTeam[]>(`/projects/${project.id}/teams`), [project.id]);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function activate(task: Task) {
    setError(null);
    try {
      await post(`/projects/${project.id}/tasks/${task.id}/activate`);
      await state.reload();
    } catch (e) {
      setError(
        e instanceof ApiError && e.code === "project_not_active"
          ? "Hãy kích hoạt project ở tab Tổng quan trước."
          : errorMessage(e),
      );
    }
  }

  return (
    <>
      {error && <div className="mb-4"><Notice>{error}</Notice></div>}
      <Card
        title="Task"
        actions={
          canManage && (
            <Button variant="primary" onClick={() => setCreating(true)}>
              Tạo task
            </Button>
          )
        }
      >
        <Loaded state={state}>
          {(rows) =>
            rows.length === 0 ? (
              <Empty>Chưa có task. Tạo task từ một dataset version để hệ thống cắt thành job.</Empty>
            ) : (
              <Table head={["Task", "Trạng thái", "Đội", "Ưu tiên", "Hoàn thành", ""]}>
                {rows.map((t) => (
                  <tr key={t.id}>
                    <Td>
                      <Link href={`/projects/${project.id}/tasks/${t.id}`} className="font-medium underline-offset-2 hover:underline">
                        {t.name}
                      </Link>
                      <span className="block text-xs text-zinc-500">{formatDate(t.created_at)}</span>
                    </Td>
                    <Td>
                      <Badge>{t.status}</Badge>
                    </Td>
                    <Td>
                      {canManage && t.status !== "delivered" ? (
                        <Select
                          value={t.team_id ?? ""}
                          onChange={async (e) => {
                            try {
                              await post(`/projects/${project.id}/tasks/${t.id}/team`, { team_id: e.target.value });
                              await state.reload();
                            } catch (err) {
                              setError(errorMessage(err));
                            }
                          }}
                        >
                          <option value="" disabled>
                            chưa giao
                          </option>
                          {teams.data?.map((team) => (
                            <option key={team.id} value={team.team_id}>
                              {team.name}
                            </option>
                          ))}
                        </Select>
                      ) : (
                        (teams.data?.find((x) => x.team_id === t.team_id)?.name ?? "—")
                      )}
                    </Td>
                    <Td>{t.priority}</Td>
                    <Td>{pct(t)}</Td>
                    <Td className="text-right">
                      {canManage && t.status === "draft" && (
                        <Button variant="primary" onClick={() => void activate(t)}>
                          Kích hoạt
                        </Button>
                      )}
                    </Td>
                  </tr>
                ))}
              </Table>
            )
          }
        </Loaded>
      </Card>
      {creating && <CreateTask project={project} onClose={() => setCreating(false)} onDone={() => void state.reload()} />}
    </>
  );
}
