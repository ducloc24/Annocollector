"use client";

import { useState } from "react";

import { Button, Card, Empty, formatDate, Input, Loaded, PageHeader, Table, Td, useAsync } from "@/components/ui";
import { get, qs } from "@/lib/api";
import type { AuditEvent, Page } from "@/lib/types";

const PAGE = 25;

export default function AuditPage() {
  const [action, setAction] = useState("");
  const [targetType, setTargetType] = useState("");
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const state = useAsync(
    () => get<Page<AuditEvent>>(`/audit-events${qs({ action, target_type: targetType, offset, limit: PAGE })}`),
    [action, targetType, offset],
  );

  return (
    <>
      <PageHeader title="Audit" subtitle="Nhật ký hành động, chỉ đọc" />
      <Card>
        <div className="mb-4 grid gap-3 sm:grid-cols-2">
          <Input placeholder="Hành động, ví dụ platform_role.grant" value={action} onChange={(e) => { setAction(e.target.value); setOffset(0); }} />
          <Input placeholder="Loại đối tượng, ví dụ user" value={targetType} onChange={(e) => { setTargetType(e.target.value); setOffset(0); }} />
        </div>
        <Loaded state={state}>
          {(page) =>
            page.items.length === 0 ? (
              <Empty>Không có sự kiện nào.</Empty>
            ) : (
              <>
                <Table head={["Thời gian", "Người thực hiện", "Hành động", "Đối tượng", ""]}>
                  {page.items.flatMap((e) => [
                    <tr key={e.id}>
                      <Td className="whitespace-nowrap">{formatDate(e.created_at)}</Td>
                      <Td>{e.actor_name}</Td>
                      <Td className="font-mono text-xs">{e.action}</Td>
                      <Td className="text-xs">
                        {e.target_type}
                        {e.target_id ? ` · ${e.target_id.slice(0, 8)}` : ""}
                      </Td>
                      <Td className="text-right">
                        <Button variant="ghost" onClick={() => setOpen(open === e.id ? null : e.id)}>
                          {open === e.id ? "Ẩn" : "Chi tiết"}
                        </Button>
                      </Td>
                    </tr>,
                    open === e.id && (
                      <tr key={`${e.id}-d`}>
                        <td colSpan={5} className="bg-zinc-50 px-3 py-3 text-xs dark:bg-zinc-950">
                          {e.reason && <p className="mb-2">Lý do: {e.reason}</p>}
                          <pre className="overflow-x-auto font-mono">
                            {JSON.stringify({ before: e.before, after: e.after, ip: e.ip }, null, 2)}
                          </pre>
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
    </>
  );
}
