"use client";

import Link from "next/link";
import { useState } from "react";

import { Badge, Card, Empty, formatDate, Loaded, PageHeader, Select, Table, Td, useAsync } from "@/components/ui";
import { get } from "@/lib/api";
import type { UserSummary } from "@/lib/types";

type Expiring = {
  id: string;
  role: string;
  granted_at: string;
  expires_at: string;
  user: UserSummary;
};

export default function ExpiringRolesPage() {
  const [days, setDays] = useState(30);
  const state = useAsync(() => get<Expiring[]>(`/platform-roles/expiring?within_days=${days}`), [days]);
  return (
    <>
      <PageHeader title="Quyền sắp hết hạn" subtitle="Quyền hết hạn sẽ tự mất; gia hạn nếu còn cần" />
      <Card
        actions={
          <Select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={7}>7 ngày</option>
            <option value={30}>30 ngày</option>
            <option value={90}>90 ngày</option>
          </Select>
        }
      >
        <Loaded state={state}>
          {(rows) =>
            rows.length === 0 ? (
              <Empty>Không có quyền nào sắp hết hạn trong {days} ngày tới.</Empty>
            ) : (
              <Table head={["Người", "Role", "Hết hạn", ""]}>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <Td>{r.user.full_name}</Td>
                    <Td>
                      <Badge tone="blue">{r.role}</Badge>
                    </Td>
                    <Td>{formatDate(r.expires_at)}</Td>
                    <Td className="text-right">
                      <Link href={`/admin/users/${r.user.id}`} className="text-sm underline underline-offset-2">
                        Gia hạn
                      </Link>
                    </Td>
                  </tr>
                ))}
              </Table>
            )
          }
        </Loaded>
      </Card>
    </>
  );
}
