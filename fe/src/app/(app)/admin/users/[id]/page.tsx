"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { type FormEvent, useState } from "react";

import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
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
import { ApiError, del, errorMessage, get, patch, post } from "@/lib/api";
import type { RoleAssignment, User } from "@/lib/types";

const ROLES = ["hr_admin", "po", "annotator", "reviewer", "project_manager", "platform_admin", "auditor"];

function GrantRole({ userId, onClose, onDone }: { userId: string; onClose: () => void; onDone: () => void }) {
  const [role, setRole] = useState("annotator");
  const [expires, setExpires] = useState("");
  const [warning, setWarning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent, acknowledge = false) {
    e.preventDefault();
    setError(null);
    try {
      await post(`/users/${userId}/platform-roles`, {
        role,
        expires_at: toIso(expires),
        acknowledge_warning: acknowledge,
      });
      onDone();
      onClose();
    } catch (err) {
      if (err instanceof ApiError && err.code === "role_conflict_warning") {
        setWarning(err.message);
      } else {
        setError(errorMessage(err));
      }
    }
  }

  return (
    <Modal title="Cấp role" onClose={onClose}>
      <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
        {error && <Notice>{error}</Notice>}
        {warning && (
          <Notice tone="amber">
            {warning}
            <div className="mt-2">
              <Button variant="primary" onClick={(e) => void submit(e, true)}>
                Vẫn cấp
              </Button>
            </div>
          </Notice>
        )}
        <Field label="Role">
          <Select value={role} onChange={(e) => { setRole(e.target.value); setWarning(null); }}>
            {ROLES.map((r) => (
              <option key={r}>{r}</option>
            ))}
          </Select>
        </Field>
        <Field label="Hết hạn (tuỳ chọn)" hint="Nên đặt với nhà thầu và thực tập">
          <Input type="datetime-local" value={expires} onChange={(e) => setExpires(e.target.value)} />
        </Field>
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Huỷ</Button>
          <Button type="submit" variant="primary">
            Cấp
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function ExtendRole({
  userId,
  assignment,
  onClose,
  onDone,
}: {
  userId: string;
  assignment: RoleAssignment;
  onClose: () => void;
  onDone: () => void;
}) {
  const [expires, setExpires] = useState("");
  const [error, setError] = useState<string | null>(null);
  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      await patch(`/users/${userId}/platform-roles/${assignment.id}`, { expires_at: toIso(expires) });
      onDone();
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    }
  }
  return (
    <Modal title={`Gia hạn ${assignment.role}`} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        {error && <Notice>{error}</Notice>}
        <Field label="Hết hạn mới" hint="Để trống nghĩa là không giới hạn">
          <Input type="datetime-local" value={expires} onChange={(e) => setExpires(e.target.value)} />
        </Field>
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Huỷ</Button>
          <Button type="submit" variant="primary">
            Lưu
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export default function UserDetailPage() {
  const { id } = useParams<{ id: string }>();
  const state = useAsync(() => get<User>(`/users/${id}`), [id]);
  const [granting, setGranting] = useState(false);
  const [extending, setExtending] = useState<RoleAssignment | null>(null);
  const [revoking, setRevoking] = useState<RoleAssignment | null>(null);
  const [offboarding, setOffboarding] = useState(false);
  const [offStatus, setOffStatus] = useState("left");
  const [link, setLink] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  return (
    <Loaded state={state}>
      {(user) => (
        <>
          <PageHeader
            title={user.full_name}
            subtitle={
              <>
                {user.email} · <Badge>{user.status}</Badge> · {user.employment_type}
              </>
            }
            actions={
              <Link href="/admin/users" className="text-sm underline underline-offset-2">
                ← Danh sách
              </Link>
            }
          />
          {notice && <div className="mb-4"><Notice tone="amber">{notice}</Notice></div>}
          <div className="flex flex-col gap-6">
            <Card
              title="Role platform"
              actions={
                user.status === "active" && (
                  <Button variant="primary" onClick={() => setGranting(true)}>
                    Cấp role
                  </Button>
                )
              }
            >
              {user.platform_roles.length === 0 ? (
                <p className="text-sm text-zinc-500">Chưa có role nào còn hiệu lực.</p>
              ) : (
                <Table head={["Role", "Cấp lúc", "Hết hạn", ""]}>
                  {user.platform_roles.map((r) => (
                    <tr key={r.id}>
                      <Td>
                        <Badge tone="blue">{r.role}</Badge>
                      </Td>
                      <Td>{formatDate(r.granted_at)}</Td>
                      <Td>{r.expires_at ? formatDate(r.expires_at) : "Không giới hạn"}</Td>
                      <Td className="text-right">
                        <div className="flex justify-end gap-2">
                          <Button onClick={() => setExtending(r)}>Gia hạn</Button>
                          <Button variant="danger" onClick={() => setRevoking(r)}>
                            Thu hồi
                          </Button>
                        </div>
                      </Td>
                    </tr>
                  ))}
                </Table>
              )}
            </Card>

            {user.status === "active" && !user.activated && (
              <Card title="Kích hoạt tài khoản">
                <p className="mb-3 text-sm text-zinc-500">Người này chưa đặt mật khẩu.</p>
                {link ? (
                  <Input readOnly value={link} onFocus={(e) => e.currentTarget.select()} />
                ) : (
                  <Button
                    onClick={async () => {
                      try {
                        const r = await post<{ activation_url: string }>(`/users/${user.id}/activation-link`);
                        setLink(r.activation_url);
                      } catch (e) {
                        setNotice(errorMessage(e));
                      }
                    }}
                  >
                    Cấp link kích hoạt mới
                  </Button>
                )}
              </Card>
            )}

            {user.status === "active" && (
              <Card title="Offboarding">
                <p className="mb-3 text-sm text-zinc-500">
                  Thu hồi mọi role, gỡ khỏi đội và project, huỷ phiên đăng nhập, trả job dở về hàng đợi.
                  Quyền mất ngay.
                </p>
                <Button variant="danger" onClick={() => setOffboarding(true)}>
                  Vô hiệu hoá người dùng
                </Button>
              </Card>
            )}
          </div>

          {granting && <GrantRole userId={user.id} onClose={() => setGranting(false)} onDone={() => void state.reload()} />}
          {extending && (
            <ExtendRole userId={user.id} assignment={extending} onClose={() => setExtending(null)} onDone={() => void state.reload()} />
          )}
          {revoking && (
            <ConfirmDialog
              title={`Thu hồi role ${revoking.role}`}
              message="Quyền trong các đội và project dựa vào role này mất hiệu lực ngay."
              danger
              askReason
              confirmLabel="Thu hồi"
              onClose={() => setRevoking(null)}
              onConfirm={async (reason) => {
                await del(`/users/${user.id}/platform-roles/${revoking.id}`, { reason });
                await state.reload();
              }}
            />
          )}
          {offboarding && (
            <ConfirmDialog
              title="Vô hiệu hoá người dùng"
              message={
                <div className="flex flex-col gap-2">
                  <span>Hành động này không đảo ngược được.</span>
                  <Select value={offStatus} onChange={(e) => setOffStatus(e.target.value)}>
                    <option value="left">Đã nghỉ việc</option>
                    <option value="suspended">Tạm khoá</option>
                  </Select>
                </div>
              }
              danger
              askReason
              confirmLabel="Vô hiệu hoá"
              onClose={() => setOffboarding(false)}
              onConfirm={async (reason) => {
                await post(`/users/${user.id}/disable`, { status: offStatus, reason });
                await state.reload();
              }}
            />
          )}
        </>
      )}
    </Loaded>
  );
}
