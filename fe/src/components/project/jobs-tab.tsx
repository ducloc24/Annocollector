"use client";

import { useState } from "react";

import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  Empty,
  Field,
  formatDate,
  Loaded,
  Modal,
  Notice,
  Select,
  Table,
  Td,
  Textarea,
  useAsync,
} from "@/components/ui";
import { errorMessage, get, post, qs } from "@/lib/api";
import type { Job, JobView, Page, Project, Workload } from "@/lib/types";

const STATUSES = [
  "unassigned",
  "assigned",
  "in_progress",
  "submitted",
  "in_review",
  "rejected",
  "escalated",
  "accepted",
  "accepted_with_fix",
];
const PAGE = 25;

function Escalations({ project }: { project: Project }) {
  const state = useAsync(() => get<Job[]>(`/projects/${project.id}/escalations`), [project.id]);
  const [open, setOpen] = useState<Job | null>(null);

  return (
    <>
      <Card title="Job bị escalate">
        <p className="mb-4 text-sm text-zinc-500">
          Reviewer không chắc, hoặc job đã hết lượt sửa. Bạn quyết định chấp nhận hay trả lại.
        </p>
        <Loaded state={state}>
          {(rows) =>
            rows.length === 0 ? (
              <Empty>Không có job nào đang chờ quyết định.</Empty>
            ) : (
              <Table head={["Job", "Số lần sửa", "Nộp lúc", ""]}>
                {rows.map((j) => (
                  <tr key={j.id}>
                    <Td>#{j.ordinal}</Td>
                    <Td>{j.rework_count}</Td>
                    <Td>{formatDate(j.submitted_at)}</Td>
                    <Td className="text-right">
                      <Button variant="primary" onClick={() => setOpen(j)}>
                        Xem và quyết định
                      </Button>
                    </Td>
                  </tr>
                ))}
              </Table>
            )
          }
        </Loaded>
      </Card>
      {open && <EscalationDialog project={project} job={open} onClose={() => setOpen(null)} onDone={() => void state.reload()} />}
    </>
  );
}

function EscalationDialog({ project, job, onClose, onDone }: { project: Project; job: Job; onClose: () => void; onDone: () => void }) {
  const view = useAsync(() => get<JobView>(`/jobs/${job.id}`), [job.id]);
  const [decision, setDecision] = useState<"accept" | "reject">("accept");
  const [reason, setReason] = useState("");
  const [guidelineIssue, setGuidelineIssue] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    try {
      await post(`/projects/${project.id}/jobs/${job.id}/escalation-decision`, {
        decision,
        reason,
        guideline_issue: guidelineIssue,
      });
      onDone();
      onClose();
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  return (
    <Modal title={`Escalation · job #${job.ordinal}`} onClose={onClose}>
      <div className="flex flex-col gap-4 text-sm">
        {error && <Notice>{error}</Notice>}
        <Loaded state={view}>
          {(v) => (
            <div className="flex flex-col gap-3">
              <p className="text-zinc-500">
                Guideline v{v.guideline.version} · {v.rounds?.length ?? 0} lượt nộp
              </p>
              {v.rounds?.map((r) => (
                <div key={r.round} className="rounded-md border border-zinc-200 p-3 dark:border-zinc-800">
                  <p className="font-medium">Lượt {r.round}</p>
                  {r.review ? (
                    <>
                      <p>
                        Quyết định: <Badge>{r.review.decision}</Badge>
                      </p>
                      {r.review.reason && <p className="text-zinc-600 dark:text-zinc-400">{r.review.reason}</p>}
                      <ul className="mt-1 list-disc pl-5 text-xs">
                        {r.review.errors.map((e, i) => (
                          <li key={i}>
                            {e.target}: {e.reason_code} ({e.severity}) {e.note}
                          </li>
                        ))}
                      </ul>
                    </>
                  ) : (
                    <p className="text-zinc-500">Chưa có review.</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </Loaded>
        <Field label="Quyết định">
          <Select value={decision} onChange={(e) => setDecision(e.target.value as "accept" | "reject")}>
            <option value="accept">Chấp nhận</option>
            <option value="reject">Trả lại cho annotator sửa</option>
          </Select>
        </Field>
        <Field label="Lý do (bắt buộc)">
          <Textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={guidelineIssue} onChange={(e) => setGuidelineIssue(e.target.checked)} />
          Nguyên nhân là guideline mơ hồ (không tính lỗi cho annotator)
        </label>
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Huỷ</Button>
          <Button variant="primary" disabled={reason.trim().length < 3} onClick={() => void submit()}>
            Lưu quyết định
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function Jobs({ project, stuck }: { project: Project; stuck: boolean }) {
  const [status, setStatus] = useState("");
  const [onlyStuck, setOnlyStuck] = useState(stuck);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string[]>([]);
  const [assigning, setAssigning] = useState<"annotate" | "review" | null>(null);
  const [unassign, setUnassign] = useState<Job | null>(null);
  const state = useAsync(
    () => get<Page<Job>>(`/projects/${project.id}/jobs${qs({ status, stuck: onlyStuck, offset, limit: PAGE })}`),
    [project.id, status, onlyStuck, offset],
  );
  const load = useAsync(() => get<Workload[]>(`/projects/${project.id}/workload`), [project.id]);

  const toggle = (id: string) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  return (
    <div className="flex flex-col gap-6">
      <Card title="Tải của từng người">
        <Loaded state={load}>
          {(rows) =>
            rows.length === 0 ? (
              <Empty>Chưa có ai trong đội của project.</Empty>
            ) : (
              <Table head={["Người", "Vai trò", "Job đang làm", "Job đang chấm"]}>
                {rows.map((w) => (
                  <tr key={w.user_id}>
                    <Td>{w.user.full_name}</Td>
                    <Td>{w.roles.join(", ")}</Td>
                    <Td>{w.annotate}</Td>
                    <Td>{w.review}</Td>
                  </tr>
                ))}
              </Table>
            )
          }
        </Loaded>
      </Card>

      <Card
        title="Job"
        actions={
          <>
            <Button disabled={selected.length === 0} onClick={() => setAssigning("annotate")}>
              Giao tay ({selected.length})
            </Button>
            <Button disabled={selected.length === 0} onClick={() => setAssigning("review")}>
              Phân reviewer
            </Button>
          </>
        }
      >
        <p className="mb-3 text-sm text-zinc-500">
          Thường ngày thành viên đội tự lấy việc. Giao tay chỉ dùng cho việc gấp hoặc ngoại lệ.
        </p>
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <Select className="max-w-52" value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); setSelected([]); }}>
            <option value="">Mọi trạng thái</option>
            {STATUSES.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </Select>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={onlyStuck} onChange={(e) => { setOnlyStuck(e.target.checked); setOffset(0); }} />
            Chỉ job kẹt quá 24 giờ
          </label>
        </div>
        <Loaded state={state}>
          {(page) =>
            page.items.length === 0 ? (
              <Empty>Không có job nào.</Empty>
            ) : (
              <>
                <Table head={["", "Job", "Trạng thái", "Người làm", "Reviewer", "Sửa", ""]}>
                  {page.items.map((j) => (
                    <tr key={j.id}>
                      <Td>
                        <input type="checkbox" checked={selected.includes(j.id)} onChange={() => toggle(j.id)} />
                      </Td>
                      <Td>
                        #{j.ordinal} {j.has_unsure && <Badge tone="amber">unsure</Badge>}
                      </Td>
                      <Td>
                        <Badge>{j.status}</Badge>
                      </Td>
                      <Td className="font-mono text-xs">{load.data?.find((w) => w.user_id === j.assignee_id)?.user.full_name ?? j.assignee_id?.slice(0, 8) ?? "—"}</Td>
                      <Td className="font-mono text-xs">{load.data?.find((w) => w.user_id === j.reviewer_id)?.user.full_name ?? j.reviewer_id?.slice(0, 8) ?? "—"}</Td>
                      <Td>{j.rework_count}</Td>
                      <Td className="text-right">
                        {["assigned", "in_progress", "rejected"].includes(j.status) && (
                          <Button variant="ghost" onClick={() => setUnassign(j)}>
                            Thu hồi
                          </Button>
                        )}
                      </Td>
                    </tr>
                  ))}
                </Table>
                <div className="mt-4 flex items-center justify-between text-sm text-zinc-500">
                  <span>
                    {offset + 1}–{Math.min(offset + PAGE, page.total)} / {page.total}
                  </span>
                  <div className="flex gap-2">
                    <Button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                      Trước
                    </Button>
                    <Button disabled={offset + PAGE >= page.total} onClick={() => setOffset(offset + PAGE)}>
                      Sau
                    </Button>
                  </div>
                </div>
              </>
            )
          }
        </Loaded>
      </Card>

      {assigning && (
        <AssignDialog
          project={project}
          mode={assigning}
          jobIds={selected}
          people={load.data ?? []}
          onClose={() => setAssigning(null)}
          onDone={() => {
            setSelected([]);
            void state.reload();
            void load.reload();
          }}
        />
      )}
      {unassign && (
        <ConfirmDialog
          title={`Thu hồi job #${unassign.ordinal}`}
          message="Job về hàng đợi; bản nháp của người đang làm bị bỏ."
          danger
          confirmLabel="Thu hồi"
          onClose={() => setUnassign(null)}
          onConfirm={async () => {
            await post(`/projects/${project.id}/jobs/${unassign.id}/unassign`);
            await state.reload();
          }}
        />
      )}
    </div>
  );
}

function AssignDialog({
  project,
  mode,
  jobIds,
  people,
  onClose,
  onDone,
}: {
  project: Project;
  mode: "annotate" | "review";
  jobIds: string[];
  people: Workload[];
  onClose: () => void;
  onDone: () => void;
}) {
  const role = mode === "annotate" ? "annotator" : "reviewer";
  const options = people.filter((p) => p.roles.includes(role));
  const [userId, setUserId] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    try {
      await post(`/projects/${project.id}/jobs/${mode === "annotate" ? "assign" : "reviewers"}`, {
        assignments: jobIds.map((job_id) => ({ job_id, user_id: userId })),
      });
      onDone();
      onClose();
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  return (
    <Modal title={mode === "annotate" ? `Giao tay ${jobIds.length} job` : `Phân reviewer cho ${jobIds.length} job`} onClose={onClose}>
      <div className="flex flex-col gap-3">
        {error && <Notice>{error}</Notice>}
        <Field label={mode === "annotate" ? "Annotator" : "Reviewer"} hint="Chỉ người thuộc đội của task">
          <Select value={userId} onChange={(e) => setUserId(e.target.value)}>
            <option value="">— chọn —</option>
            {options.map((p) => (
              <option key={p.user_id} value={p.user_id}>
                {p.user.full_name} (đang làm {p.annotate}, đang chấm {p.review})
              </option>
            ))}
          </Select>
        </Field>
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Huỷ</Button>
          <Button variant="primary" disabled={!userId} onClick={() => void submit()}>
            Xác nhận
          </Button>
        </div>
      </div>
    </Modal>
  );
}

export function JobsTab({ project, mode, stuck = false }: { project: Project; mode: "jobs" | "escalations"; stuck?: boolean }) {
  return mode === "jobs" ? <Jobs project={project} stuck={stuck} /> : <Escalations project={project} />;
}
