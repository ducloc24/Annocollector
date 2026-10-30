"use client";

import { useState } from "react";

import { Button, Card, Empty, formatDate, Loaded, Table, Td, useAsync } from "@/components/ui";
import { get, qs } from "@/lib/api";
import type { AuditEvent, Page, Project } from "@/lib/types";

const PAGE = 25;

export function AuditTab({ project }: { project: Project }) {
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const state = useAsync(
    () => get<Page<AuditEvent>>(`/projects/${project.id}/audit-events${qs({ offset, limit: PAGE })}`),
    [project.id, offset],
  );
  return (
    <Card title="Nhật ký của project">
      <Loaded state={state}>
        {(page) =>
          page.items.length === 0 ? (
            <Empty>Chưa có sự kiện nào.</Empty>
          ) : (
            <>
              <Table head={["Thời gian", "Người thực hiện", "Hành động", ""]}>
                {page.items.flatMap((e) => [
                  <tr key={e.id}>
                    <Td className="whitespace-nowrap">{formatDate(e.created_at)}</Td>
                    <Td>{e.actor_name}</Td>
                    <Td className="font-mono text-xs">{e.action}</Td>
                    <Td className="text-right">
                      <Button variant="ghost" onClick={() => setOpen(open === e.id ? null : e.id)}>
                        {open === e.id ? "Ẩn" : "Chi tiết"}
                      </Button>
                    </Td>
                  </tr>,
                  open === e.id && (
                    <tr key={`${e.id}-d`}>
                      <td colSpan={4} className="bg-zinc-50 px-3 py-3 text-xs dark:bg-zinc-950">
                        {e.reason && <p className="mb-2">Lý do: {e.reason}</p>}
                        <pre className="overflow-x-auto font-mono">{JSON.stringify({ before: e.before, after: e.after }, null, 2)}</pre>
                      </td>
                    </tr>
                  ),
                ])}
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
  );
}
