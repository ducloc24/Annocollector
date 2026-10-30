"use client";

import { Badge, Card, Empty, Loaded, Table, Td, useAsync } from "@/components/ui";
import { get } from "@/lib/api";
import type { Project, QualityReport } from "@/lib/types";

export const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`);

export function QualityTab({ project }: { project: Project }) {
  const state = useAsync(() => get<QualityReport>(`/projects/${project.id}/quality`), [project.id]);
  const full = project.my_permissions.includes("quality.read") && project.my_roles.some((r) => r !== "annotator" && r !== "reviewer");

  return (
    <Loaded state={state}>
      {(r) => (
        <div className="flex flex-col gap-6">
          <div className="grid gap-4 sm:grid-cols-3">
            <Card>
              <p className="text-2xl font-semibold">{r.jobs_closed}</p>
              <p className="text-sm text-zinc-500">job đã được chấp nhận</p>
            </Card>
            <Card>
              <p className="text-2xl font-semibold">{pct(r.first_pass_rate)}</p>
              <p className="text-sm text-zinc-500">đạt ngay lần đầu (mục tiêu ≥ 90%)</p>
            </Card>
            <Card>
              <p className="text-2xl font-semibold">{pct(r.reject_rate)}</p>
              <p className="text-sm text-zinc-500">tỷ lệ bị trả lại</p>
            </Card>
          </div>

          <Card title="Lỗi thường gặp">
            {r.reason_codes.length === 0 ? (
              <Empty>Chưa có lỗi nào được ghi.</Empty>
            ) : (
              <>
                <Table head={["Mã lỗi", "Mức", "Số lần"]}>
                  {r.reason_codes.map((c) => (
                    <tr key={c.reason_code}>
                      <Td className="font-mono text-xs">{c.reason_code}</Td>
                      <Td>
                        <Badge tone={c.severity === "critical" ? "red" : c.severity === "major" ? "amber" : "zinc"}>{c.severity}</Badge>
                      </Td>
                      <Td>{c.count}</Td>
                    </tr>
                  ))}
                </Table>
                <p className="mt-3 text-xs text-zinc-500">
                  Nhiều người cùng mắc một lỗi thường là guideline mơ hồ; sửa guideline thay vì xử lý từng cá nhân.
                </p>
              </>
            )}
          </Card>

          <Card title="Annotator">
            {r.annotators.length === 0 ? (
              <Empty>Chưa có số liệu.</Empty>
            ) : (
              <Table head={["Người", "Job đạt", "Đạt lần đầu", "Số lần sửa TB", "Tỷ lệ bị trả", "Độ chính xác gold"]}>
                {r.annotators.map((a) => (
                  <tr key={a.user_id}>
                    <Td>{a.name}</Td>
                    <Td>{a.jobs_closed}</Td>
                    <Td>{pct(a.first_pass_rate)}</Td>
                    <Td>{a.avg_rework ?? "—"}</Td>
                    <Td>{pct(a.reject_rate)}</Td>
                    <Td>{pct(a.gold_accuracy)}</Td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>

          <Card title="Reviewer">
            {r.reviewers.length === 0 ? (
              <Empty>Chưa có số liệu.</Empty>
            ) : (
              <Table head={["Người", "Job đã chấm", "Tỷ lệ trả lại", "Bị đổi quyết định"]}>
                {r.reviewers.map((v) => (
                  <tr key={v.user_id}>
                    <Td>{v.name}</Td>
                    <Td>{v.reviews}</Td>
                    <Td>{pct(v.reject_rate)}</Td>
                    <Td>{v.overridden}</Td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>

          {full && r.trend.length > 0 && (
            <Card title="Xu hướng theo tuần">
              <Table head={["Tuần", "Job", "Đạt lần đầu"]}>
                {r.trend.map((t) => (
                  <tr key={t.week}>
                    <Td>{t.week}</Td>
                    <Td>{t.jobs}</Td>
                    <Td>{pct(t.first_pass_rate)}</Td>
                  </tr>
                ))}
              </Table>
              <p className="mt-3 text-xs text-zinc-500">Nhìn theo xu hướng: một con số trên ngưỡng nhưng giảm dần vài tuần vẫn là vấn đề.</p>
            </Card>
          )}
        </div>
      )}
    </Loaded>
  );
}
