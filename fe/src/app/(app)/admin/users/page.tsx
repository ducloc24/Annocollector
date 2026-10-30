"use client";

import Link from "next/link";
import { type FormEvent, useState } from "react";

import {
  Badge,
  Button,
  Card,
  Empty,
  Field,
  Input,
  Loaded,
  Modal,
  Notice,
  PageHeader,
  Select,
  Table,
  Td,
  useAsync,
} from "@/components/ui";
import { errorMessage, get, post, qs } from "@/lib/api";
import type { Page, User } from "@/lib/types";

const PAGE = 20;

type Created = { user: User; activation_url: string; activation_expires_at: string };

function CreateUser({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [form, setForm] = useState({ full_name: "", email: "", employee_code: "", employment_type: "full_time" });
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<Created | null>(null);
  const [copied, setCopied] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const result = await post<Created>("/users", {
        ...form,
        employee_code: form.employee_code || null,
      });
      setCreated(result);
      onCreated();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  if (created) {
    return (
      <Modal title="Đã tạo người dùng" onClose={onClose}>
        <div className="flex flex-col gap-3 text-sm">
          <Notice tone="green">
            {created.user.full_name} đã được tạo. Gửi link dưới đây cho họ để đặt mật khẩu (dùng một lần,
            hết hạn sau 72 giờ). Link chỉ hiện ở đây một lần.
          </Notice>
          <Input readOnly value={created.activation_url} onFocus={(e) => e.currentTarget.select()} />
          <div className="flex justify-end gap-2">
            <Button
              onClick={async () => {
                await navigator.clipboard.writeText(created.activation_url);
                setCopied(true);
              }}
            >
              {copied ? "Đã sao chép" : "Sao chép link"}
            </Button>
            <Button variant="primary" onClick={onClose}>
              Xong
            </Button>
          </div>
        </div>
      </Modal>
    );
  }

  return (
    <Modal title="Tạo người dùng" onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        {error && <Notice>{error}</Notice>}
        <Field label="Họ tên">
          <Input required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
        </Field>
        <Field label="Email">
          <Input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </Field>
        <Field label="Mã nhân viên (tuỳ chọn)">
          <Input value={form.employee_code} onChange={(e) => setForm({ ...form, employee_code: e.target.value })} />
        </Field>
        <Field label="Loại hợp đồng">
          <Select value={form.employment_type} onChange={(e) => setForm({ ...form, employment_type: e.target.value })}>
            <option value="full_time">Toàn thời gian</option>
            <option value="contractor">Nhà thầu</option>
            <option value="intern">Thực tập</option>
          </Select>
        </Field>
        <p className="text-xs text-zinc-500">Không cần chọn project; PO sẽ chọn đội cho project sau.</p>
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Huỷ</Button>
          <Button type="submit" variant="primary">
            Tạo
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export default function UsersPage() {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [role, setRole] = useState("");
  const [offset, setOffset] = useState(0);
  const [creating, setCreating] = useState(false);
  const state = useAsync(
    () => get<Page<User>>(`/users${qs({ q, status, role, offset, limit: PAGE })}`),
    [q, status, role, offset],
  );

  return (
    <>
      <PageHeader
        title="Người dùng"
        subtitle="Tạo tài khoản, cấp quyền, offboarding"
        actions={
          <Button variant="primary" onClick={() => setCreating(true)}>
            Tạo người dùng
          </Button>
        }
      />
      <Card>
        <div className="mb-4 grid gap-3 sm:grid-cols-3">
          <Input
            placeholder="Tìm theo tên, email, mã"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setOffset(0);
            }}
          />
          <Select value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }}>
            <option value="">Mọi trạng thái</option>
            <option value="active">Đang hoạt động</option>
            <option value="suspended">Tạm khoá</option>
            <option value="left">Đã nghỉ</option>
          </Select>
          <Select value={role} onChange={(e) => { setRole(e.target.value); setOffset(0); }}>
            <option value="">Mọi role</option>
            {["hr_admin", "po", "annotator", "reviewer", "project_manager", "platform_admin", "auditor"].map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </Select>
        </div>
        <Loaded state={state}>
          {(page) =>
            page.items.length === 0 ? (
              <Empty>Không có người dùng nào.</Empty>
            ) : (
              <>
                <Table head={["Họ tên", "Email", "Role", "Trạng thái", ""]}>
                  {page.items.map((u) => (
                    <tr key={u.id}>
                      <Td>
                        <Link href={`/admin/users/${u.id}`} className="font-medium underline-offset-2 hover:underline">
                          {u.full_name}
                        </Link>
                        {u.employee_code && <span className="ml-2 text-xs text-zinc-500">{u.employee_code}</span>}
                      </Td>
                      <Td>{u.email}</Td>
                      <Td>
                        <div className="flex flex-wrap gap-1">
                          {u.platform_roles.map((r) => (
                            <Badge key={r.id} tone="blue">
                              {r.role}
                            </Badge>
                          ))}
                        </div>
                      </Td>
                      <Td>
                        <Badge>{u.status}</Badge>
                        {u.status === "active" && !u.activated && (
                          <span className="ml-2 text-xs text-amber-600">chưa kích hoạt</span>
                        )}
                      </Td>
                      <Td className="text-right">
                        <Link href={`/admin/users/${u.id}`} className="text-sm underline underline-offset-2">
                          Chi tiết
                        </Link>
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
      {creating && <CreateUser onClose={() => setCreating(false)} onCreated={() => void state.reload()} />}
    </>
  );
}
