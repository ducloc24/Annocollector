"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { Badge, Card, Empty, Loaded, Notice, PageHeader, Table, Td, useAsync } from "@/components/ui";
import { pct } from "@/components/project/quality-tab";
import { get } from "@/lib/api";
import type { TeamOverviewRow, TeamQuality } from "@/lib/types";

type Alert = { level: "red" | "amber"; text: string };

export default function TeamLeadPage() {
  const { id } = useParams<{ id: string }>();
  const overview = useAsync(() => get<TeamOverviewRow[]>(`/teams/${id}/overview`), [id]);
  const quality = useAsync(() => get<TeamQuality>(`/teams/${id}/quality`), [id]);
  const alerts = useAsync(() => get<Alert[]>(`/teams/${id}/alerts`), [id]);

  return (
    <>
      <PageHeader
        title="Đội của tôi"
        subtitle="Số liệu của đội trên mọi project đội đang làm. Bạn chỉ thấy số liệu tổng hợp, không thấy nội dung job của người khác."
        actions={
          <Link href="/" className="text-sm underline underline-offset-2">
            ← Việc cần làm
          </Link>
        }
      />
      <div className="flex flex-col gap-6">
        <Loaded state={alerts}>
          {(rows) =>
            rows.length > 0 && (
              <div className="flex flex-col gap-2">
                {rows.map((a) => (
                  <Notice key={a.text} tone={a.level}>
                    {a.text}
                  </Notice>
                ))}
              </div>
            )
          }
        </Loaded>

        <Card title="Tải của từng thành viên">
          <Loaded state={overview}>
            {(rows) =>
              rows.length === 0 ? (
                <Empty>Đội chưa có thành viên.</Empty>
              ) : (
                <Table head={["Người", "Vai trò", "Đang làm", "Đang chấm", "Job đã đạt"]}>
                  {rows.map((r) => (
                    <tr key={r.user.id}>
                      <Td>
                        {r.user.full_name} {r.is_lead && <Badge tone="blue">trưởng nhóm</Badge>}
                      </Td>
                      <Td>{r.team_role}</Td>
                      <Td>{r.annotating}</Td>
                      <Td>{r.reviewing}</Td>
                      <Td>{r.jobs_accepted}</Td>
                    </tr>
                  ))}
                </Table>
              )
            }
          </Loaded>
        </Card>

        <Card title="Chất lượng để kèm cặp">
          <Loaded state={quality}>
            {(q) =>
              q.members.length === 0 ? (
                <Empty>Chưa có số liệu.</Empty>
              ) : (
                <>
                  <Table head={["Người", "Job đạt", "Đạt lần đầu", "Tỷ lệ bị trả", "Lỗi hay gặp", ""]}>
                    {q.members.map((m) => (
                      <tr key={m.user_id}>
                        <Td>{m.name}</Td>
                        <Td>{m.jobs_closed}</Td>
                        <Td>{pct(m.first_pass_rate)}</Td>
                        <Td>{pct(m.reject_rate)}</Td>
                        <Td className="text-xs">{m.top_errors.map((e) => `${e.reason_code} ×${e.count}`).join(", ") || "—"}</Td>
                        <Td>{m.coaching_flag && <Badge tone="amber">nên kèm cặp</Badge>}</Td>
                      </tr>
                    ))}
                  </Table>
                  <p className="mt-3 text-xs text-zinc-500">
                    “Nên kèm cặp” nghĩa là người đó bị ghi cùng một mã lỗi từ hai lần trở lên: thường là hiểu sai guideline, cần hướng dẫn chứ không chỉ trừ điểm.
                  </p>
                </>
              )
            }
          </Loaded>
        </Card>

        <Loaded state={quality}>
          {(q) =>
            q.trend.length > 0 && (
              <Card title="Xu hướng theo tuần">
                <Table head={["Tuần", "Job", "Đạt lần đầu"]}>
                  {q.trend.map((t) => (
                    <tr key={t.week}>
                      <Td>{t.week}</Td>
                      <Td>{t.jobs}</Td>
                      <Td>{pct(t.first_pass_rate)}</Td>
                    </tr>
                  ))}
                </Table>
              </Card>
            )
          }
        </Loaded>
      </div>
    </>
  );
}
