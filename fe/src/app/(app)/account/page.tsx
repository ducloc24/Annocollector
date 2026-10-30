"use client";

import { type FormEvent, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { Badge, Button, Card, Field, formatDate, Input, Loaded, Notice, PageHeader, Table, Td, useAsync } from "@/components/ui";
import { pct } from "@/components/project/quality-tab";
import { errorMessage, get, post } from "@/lib/api";
import type { MyQuality } from "@/lib/types";

export default function AccountPage() {
  const { user, teams, projects, reload } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [message, setMessage] = useState<{ tone: "green" | "red"; text: string } | null>(null);
  const quality = useAsync(() => get<MyQuality[]>("/me/quality"));

  async function change(e: FormEvent) {
    e.preventDefault();
    setMessage(null);
    try {
      await post("/auth/change-password", { current_password: current, new_password: next });
      setCurrent("");
      setNext("");
      setMessage({ tone: "green", text: "Đã đổi mật khẩu. Các phiên khác đã bị đăng xuất." });
      await reload();
    } catch (err) {
      setMessage({ tone: "red", text: errorMessage(err) });
    }
  }

  if (!user) return null;
  return (
    <>
      <PageHeader title="Tài khoản" subtitle={user.email} />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Thông tin">
          <dl className="grid grid-cols-[8rem_1fr] gap-y-2 text-sm">
            <dt className="text-zinc-500">Họ tên</dt>
            <dd>{user.full_name}</dd>
            <dt className="text-zinc-500">Mã nhân viên</dt>
            <dd>{user.employee_code ?? "—"}</dd>
            <dt className="text-zinc-500">Loại hợp đồng</dt>
            <dd>{user.employment_type}</dd>
          </dl>
        </Card>
        <Card title="Đổi mật khẩu">
          <form onSubmit={change} className="flex flex-col gap-3">
            {message && <Notice tone={message.tone}>{message.text}</Notice>}
            <Field label="Mật khẩu hiện tại">
              <Input type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} />
            </Field>
            <Field label="Mật khẩu mới" hint="Tối thiểu 10 ký tự">
              <Input type="password" autoComplete="new-password" minLength={10} required value={next} onChange={(e) => setNext(e.target.value)} />
            </Field>
            <Button type="submit" variant="primary">
              Đổi mật khẩu
            </Button>
          </form>
        </Card>
        <Card title="Quyền của tôi">
          {user.platform_roles.length === 0 ? (
            <p className="text-sm text-zinc-500">Chưa có role nào.</p>
          ) : (
            <Table head={["Role", "Hết hạn"]}>
              {user.platform_roles.map((r) => (
                <tr key={r.id}>
                  <Td>
                    <Badge tone="blue">{r.role}</Badge>
                  </Td>
                  <Td>{r.expires_at ? formatDate(r.expires_at) : "Không giới hạn"}</Td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
        <Card title="Chất lượng của tôi" className="lg:col-span-2">
          <Loaded state={quality}>
            {(rows) =>
              rows.length === 0 ? (
                <p className="text-sm text-zinc-500">Chưa có số liệu.</p>
              ) : (
                <Table head={["Project", "Vai trò", "Job đạt", "Đạt lần đầu", "Tỷ lệ bị trả", "Đã chấm"]}>
                  {rows.flatMap((r) => [
                    r.as_annotator && (
                      <tr key={`${r.project.id}-a`}>
                        <Td>{r.project.name}</Td>
                        <Td>annotator</Td>
                        <Td>{r.as_annotator.jobs_closed}</Td>
                        <Td>{pct(r.as_annotator.first_pass_rate)}</Td>
                        <Td>{pct(r.as_annotator.reject_rate)}</Td>
                        <Td>—</Td>
                      </tr>
                    ),
                    r.as_reviewer && (
                      <tr key={`${r.project.id}-r`}>
                        <Td>{r.project.name}</Td>
                        <Td>reviewer</Td>
                        <Td>—</Td>
                        <Td>—</Td>
                        <Td>{pct(r.as_reviewer.reject_rate)}</Td>
                        <Td>{r.as_reviewer.reviews}</Td>
                      </tr>
                    ),
                  ])}
                </Table>
              )
            }
          </Loaded>
        </Card>
        <Card title="Đội và project">
          <ul className="flex flex-col gap-2 text-sm">
            {teams.map((t) => (
              <li key={t.team_id}>
                Đội <strong>{t.name}</strong> · {t.team_role}
                {t.is_lead ? " · trưởng nhóm" : ""}
              </li>
            ))}
            {projects.map((p) => (
              <li key={p.id}>
                Project <strong>{p.name}</strong> · {p.my_roles.join(", ")}
              </li>
            ))}
            {teams.length + projects.length === 0 && <li className="text-zinc-500">Chưa thuộc đội hay project nào.</li>}
          </ul>
        </Card>
      </div>
    </>
  );
}
