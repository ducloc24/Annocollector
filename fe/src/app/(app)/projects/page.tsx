"use client";

import Link from "next/link";

import { useAuth } from "@/components/auth-provider";
import { Badge, Button, Card, Empty, Loaded, PageHeader, Table, Td, useAsync } from "@/components/ui";
import { get } from "@/lib/api";
import type { Progress } from "@/lib/types";

export default function ProjectsPage() {
  const { projects, can } = useAuth();
  const progress = useAsync(async () => {
    const entries = await Promise.all(
      projects
        .filter((p) => p.my_permissions.includes("progress.read"))
        .map(async (p) => [p.id, await get<Progress>(`/projects/${p.id}/progress`)] as const),
    );
    return Object.fromEntries(entries);
  }, [projects.map((p) => p.id).join(",")]);

  return (
    <>
      <PageHeader
        title="Project"
        subtitle="Các project bạn tham gia, kèm tiến độ"
        actions={
          can("project.create") && (
            <Link href="/projects/new">
              <Button variant="primary">Tạo project</Button>
            </Link>
          )
        }
      />
      <Card>
        {projects.length === 0 ? (
          <Empty>Bạn chưa thuộc project nào.</Empty>
        ) : (
          <Loaded state={progress}>
            {(byId) => (
              <Table head={["Project", "Vai trò", "Trạng thái", "Hoàn thành", "Cần chú ý"]}>
                {projects.map((p) => {
                  const pr = byId[p.id];
                  return (
                    <tr key={p.id}>
                      <Td>
                        <Link href={`/projects/${p.id}`} className="font-medium underline-offset-2 hover:underline">
                          {p.name}
                        </Link>
                        <span className="ml-2 text-xs text-zinc-500">{p.code}</span>
                      </Td>
                      <Td>{p.my_roles.join(", ")}</Td>
                      <Td>
                        <Badge>{p.status}</Badge>
                      </Td>
                      <Td>{pr ? `${Math.round(pr.completion_rate * 100)}% (${pr.jobs_total} job)` : "—"}</Td>
                      <Td>
                        <div className="flex gap-1">
                          {pr && pr.by_status.escalated > 0 && <Badge tone="red">{pr.by_status.escalated} escalation</Badge>}
                          {pr && pr.stuck > 0 && <Badge tone="amber">{pr.stuck} kẹt</Badge>}
                        </div>
                      </Td>
                    </tr>
                  );
                })}
              </Table>
            )}
          </Loaded>
        )}
      </Card>
    </>
  );
}
