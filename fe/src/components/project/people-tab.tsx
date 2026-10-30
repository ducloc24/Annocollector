"use client";

import { type FormEvent, useState } from "react";

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
  useAsync,
} from "@/components/ui";
import { ApiError, del, errorMessage, get, post } from "@/lib/api";
import type { Member, Project, ProjectTeam, TeamSummary, UserSummary } from "@/lib/types";

type Linked = { link: ProjectTeam; warnings: string[] };

function AddMember({ project, onClose, onDone }: { project: Project; onClose: () => void; onDone: () => void }) {
  const [role, setRole] = useState<"manager" | "viewer" | "owner">("manager");
  const [userId, setUserId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const candidates = useAsync(() => get<UserSummary[]>(`/projects/${project.id}/candidates?role=${role}`), [role]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      await post(`/projects/${project.id}/members`, { user_id: userId, role });
      onDone();
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <Modal title="Thêm thành viên quản lý" onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        {error && <Notice>{error}</Notice>}
        <p className="text-xs text-zinc-500">
          Annotator và reviewer không thêm lẻ ở đây; họ vào project qua đội đánh giá.
        </p>
        <Field label="Vai trò">
          <Select value={role} onChange={(e) => { setRole(e.target.value as typeof role); setUserId(""); }}>
            <option value="manager">Manager (điều phối)</option>
            <option value="viewer">Viewer (chỉ xem)</option>
            <option value="owner">Owner (đồng sở hữu)</option>
          </Select>
        </Field>
        <Field label="Người">
          <Select required value={userId} onChange={(e) => setUserId(e.target.value)}>
            <option value="">— chọn —</option>
            {candidates.data?.map((u) => (
              <option key={u.id} value={u.id}>
                {u.full_name} ({u.email})
              </option>
            ))}
          </Select>
        </Field>
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Huỷ</Button>
          <Button type="submit" variant="primary" disabled={!userId}>
            Thêm
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function LinkTeam({
  project,
  linked,
  onClose,
  onDone,
}: {
  project: Project;
  linked: string[];
  onClose: () => void;
  onDone: (warnings: string[]) => void;
}) {
  const teams = useAsync(() => get<TeamSummary[]>("/teams?status=active"));
  const [teamId, setTeamId] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      const result = await post<Linked>(`/projects/${project.id}/teams`, { team_id: teamId });
      onDone(result.warnings);
      onClose();
    } catch (err) {
      if (err instanceof ApiError && err.code === "role_conflict") {
        const users = (err.details as { users: { full_name: string }[] }).users;
        setError(`Những người này sẽ vừa là annotator vừa là reviewer: ${users.map((u) => u.full_name).join(", ")}`);
      } else if (err instanceof ApiError && err.code === "team_missing_role") {
        setError("Đội cần ít nhất một annotator và một reviewer. Nhờ HR bổ sung.");
      } else {
        setError(errorMessage(err));
      }
    }
  }

  return (
    <Modal title="Gắn đội đánh giá" onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        {error && <Notice>{error}</Notice>}
        <Field label="Đội">
          <Select required value={teamId} onChange={(e) => setTeamId(e.target.value)}>
            <option value="">— chọn —</option>
            {teams.data
              ?.filter((t) => !linked.includes(t.id))
              .map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({t.annotators} annotator, {t.reviewers} reviewer)
                </option>
              ))}
          </Select>
        </Field>
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Huỷ</Button>
          <Button type="submit" variant="primary" disabled={!teamId}>
            Gắn đội
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export function PeopleTab({ project }: { project: Project }) {
  const canManage = project.my_permissions.includes("member.manage");
  const members = useAsync(() => get<Member[]>(`/projects/${project.id}/members`), [project.id]);
  const teams = useAsync(() => get<ProjectTeam[]>(`/projects/${project.id}/teams`), [project.id]);
  const [adding, setAdding] = useState(false);
  const [linking, setLinking] = useState(false);
  const [removeMember, setRemoveMember] = useState<Member | null>(null);
  const [unlink, setUnlink] = useState<ProjectTeam | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);

  return (
    <div className="flex flex-col gap-6">
      {warnings.map((w) => (
        <Notice key={w} tone="amber">
          {w}
        </Notice>
      ))}
      <Card
        title="Đội đánh giá"
        actions={
          canManage && (
            <Button variant="primary" onClick={() => setLinking(true)}>
              Gắn đội
            </Button>
          )
        }
      >
        <Loaded state={teams}>
          {(rows) =>
            rows.length === 0 ? (
              <Empty>Chưa gắn đội nào. Cần ít nhất một đội để annotator và reviewer làm việc.</Empty>
            ) : (
              <Table head={["Đội", "Annotator", "Reviewer", "Gắn lúc", ""]}>
                {rows.map((t) => (
                  <tr key={t.id}>
                    <Td>
                      {t.name} <span className="text-xs text-zinc-500">{t.code}</span>
                    </Td>
                    <Td>{t.annotators}</Td>
                    <Td>{t.reviewers}</Td>
                    <Td>{formatDate(t.assigned_at)}</Td>
                    <Td className="text-right">
                      {canManage && (
                        <Button variant="danger" onClick={() => setUnlink(t)}>
                          Gỡ
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

      <Card
        title="Quản lý và người xem"
        actions={
          canManage && (
            <Button onClick={() => setAdding(true)}>Thêm</Button>
          )
        }
      >
        <Loaded state={members}>
          {(rows) => (
            <Table head={["Người", "Vai trò", "Từ", ""]}>
              {rows.map((m) => (
                <tr key={m.id}>
                  <Td>
                    {m.user.full_name} <span className="text-xs text-zinc-500">{m.user.email}</span>
                  </Td>
                  <Td>
                    <Badge tone="blue">{m.role}</Badge>
                  </Td>
                  <Td>{formatDate(m.assigned_at)}</Td>
                  <Td className="text-right">
                    {canManage && (
                      <Button variant="danger" onClick={() => setRemoveMember(m)}>
                        Gỡ
                      </Button>
                    )}
                  </Td>
                </tr>
              ))}
            </Table>
          )}
        </Loaded>
      </Card>

      {adding && <AddMember project={project} onClose={() => setAdding(false)} onDone={() => void members.reload()} />}
      {linking && (
        <LinkTeam
          project={project}
          linked={teams.data?.map((t) => t.team_id) ?? []}
          onClose={() => setLinking(false)}
          onDone={(w) => {
            setWarnings(w);
            void teams.reload();
          }}
        />
      )}
      {removeMember && (
        <ConfirmDialog
          title={`Gỡ ${removeMember.user.full_name}`}
          danger
          confirmLabel="Gỡ"
          onClose={() => setRemoveMember(null)}
          onConfirm={async () => {
            await del(`/projects/${project.id}/members/${removeMember.id}`);
            await members.reload();
          }}
        />
      )}
      {unlink && (
        <ConfirmDialog
          title={`Gỡ đội ${unlink.name}`}
          message="Thành viên đội mất quyền trong project; job đang làm dở của họ về hàng đợi. Đội còn task đang chạy thì phải giao task cho đội khác trước."
          danger
          confirmLabel="Gỡ đội"
          onClose={() => setUnlink(null)}
          onConfirm={async () => {
            await del(`/projects/${project.id}/teams/${unlink.id}`);
            await teams.reload();
          }}
        />
      )}
    </div>
  );
}
