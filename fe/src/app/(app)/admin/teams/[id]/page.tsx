"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { type FormEvent, useState } from "react";

import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  Empty,
  Field,
  formatDate,
  Input,
  Loaded,
  Modal,
  Notice,
  PageHeader,
  Select,
  Table,
  Td,
  toIso,
  useAsync,
} from "@/components/ui";
import { ApiError, del, errorMessage, get, patch, post, qs } from "@/lib/api";
import type { Page, TeamDetail, TeamMember, User } from "@/lib/types";

function AddMember({ teamId, onClose, onDone }: { teamId: string; onClose: () => void; onDone: () => void }) {
  const [role, setRole] = useState<"annotator" | "reviewer">("annotator");
  const [userId, setUserId] = useState("");
  const [expires, setExpires] = useState("");
  const [error, setError] = useState<string | null>(null);
  const candidates = useAsync(() => get<Page<User>>(`/users${qs({ role, status: "active", limit: 100 })}`), [role]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await post(`/teams/${teamId}/members`, { user_id: userId, team_role: role, expires_at: toIso(expires) });
      onDone();
      onClose();
    } catch (err) {
      setError(
        err instanceof ApiError && err.code === "role_conflict"
          ? "Người này sẽ vừa là annotator vừa là reviewer ở một project đang dùng đội này."
          : errorMessage(err),
      );
    }
  }

  return (
    <Modal title="Thêm thành viên" onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        {error && <Notice>{error}</Notice>}
        <Field label="Vai trò trong đội">
          <Select value={role} onChange={(e) => { setRole(e.target.value as "annotator" | "reviewer"); setUserId(""); }}>
            <option value="annotator">Annotator</option>
            <option value="reviewer">Reviewer</option>
          </Select>
        </Field>
        <Field label="Người" hint="Chỉ hiện người đã có role platform tương ứng">
          <Select required value={userId} onChange={(e) => setUserId(e.target.value)}>
            <option value="">— chọn —</option>
            {candidates.data?.items.map((u) => (
              <option key={u.id} value={u.id}>
                {u.full_name} ({u.email})
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Hết hạn (tuỳ chọn)">
          <Input type="datetime-local" value={expires} onChange={(e) => setExpires(e.target.value)} />
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

export default function TeamDetailPage() {
  const { id } = useParams<{ id: string }>();
  const state = useAsync(() => get<TeamDetail>(`/teams/${id}`), [id]);
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<TeamMember | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function update(member: TeamMember, changes: Record<string, unknown>) {
    setNotice(null);
    try {
      await patch(`/teams/${id}/members/${member.id}`, changes);
      await state.reload();
    } catch (e) {
      setNotice(errorMessage(e));
    }
  }

  return (
    <Loaded state={state}>
      {(team) => {
        const missing: string[] = [];
        if (team.annotators === 0) missing.push("annotator");
        if (team.reviewers === 0) missing.push("reviewer");
        return (
          <>
            <PageHeader
              title={team.name}
              subtitle={
                <>
                  {team.code} · <Badge>{team.status}</Badge>
                </>
              }
              actions={
                <>
                  <Link href="/admin/teams" className="text-sm underline underline-offset-2">
                    ← Danh sách
                  </Link>
                  <Button variant="primary" onClick={() => setAdding(true)}>
                    Thêm thành viên
                  </Button>
                </>
              }
            />
            {notice && <div className="mb-4"><Notice>{notice}</Notice></div>}
            {missing.length > 0 && (
              <div className="mb-4">
                <Notice tone="amber">
                  Đội chưa có {missing.join(" và ")}. Cần ít nhất một annotator và một reviewer thì PO mới gắn đội vào
                  project được.
                </Notice>
              </div>
            )}
            <Card title={`Thành viên (${team.annotators} annotator, ${team.reviewers} reviewer)`}>
              {team.members.length === 0 ? (
                <Empty>Chưa có thành viên.</Empty>
              ) : (
                <Table head={["Người", "Vai trò", "Trưởng nhóm", "Hết hạn", ""]}>
                  {team.members.map((m) => (
                    <tr key={m.id}>
                      <Td>
                        {m.user.full_name}
                        <span className="ml-2 text-xs text-zinc-500">{m.user.email}</span>
                      </Td>
                      <Td>
                        <Select
                          value={m.team_role}
                          onChange={(e) => void update(m, { team_role: e.target.value })}
                        >
                          <option value="annotator">annotator</option>
                          <option value="reviewer">reviewer</option>
                        </Select>
                      </Td>
                      <Td>
                        {m.is_lead ? (
                          <Button onClick={() => void update(m, { is_lead: false })}>Bỏ trưởng nhóm</Button>
                        ) : (
                          <Button onClick={() => void update(m, { is_lead: true })}>Chỉ định</Button>
                        )}
                      </Td>
                      <Td>{m.expires_at ? formatDate(m.expires_at) : "—"}</Td>
                      <Td className="text-right">
                        <Button variant="danger" onClick={() => setRemoving(m)}>
                          Gỡ
                        </Button>
                      </Td>
                    </tr>
                  ))}
                </Table>
              )}
            </Card>
            {adding && <AddMember teamId={team.id} onClose={() => setAdding(false)} onDone={() => void state.reload()} />}
            {removing && (
              <ConfirmDialog
                title={`Gỡ ${removing.user.full_name} khỏi đội`}
                message="Job đang làm dở của họ trong các project dùng đội này sẽ về lại hàng đợi."
                danger
                askReason
                confirmLabel="Gỡ"
                onClose={() => setRemoving(null)}
                onConfirm={async (reason) => {
                  await del(`/teams/${id}/members/${removing.id}`, { reason });
                  await state.reload();
                }}
              />
            )}
          </>
        );
      }}
    </Loaded>
  );
}
