"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { Badge, Button, Card, Empty, Field, Input, Loaded, Modal, Notice, PageHeader, Table, Td, Textarea, useAsync } from "@/components/ui";
import { errorMessage, get, post } from "@/lib/api";
import type { TeamSummary } from "@/lib/types";

export default function TeamsPage() {
  const router = useRouter();
  const state = useAsync(() => get<TeamSummary[]>("/teams"));
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ code: "", name: "", description: "" });
  const [error, setError] = useState<string | null>(null);

  async function create(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const team = await post<TeamSummary>("/teams", { ...form, description: form.description || null });
      router.push(`/admin/teams/${team.id}`);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <>
      <PageHeader
        title="Đội đánh giá"
        subtitle="Nhóm annotator và reviewer. PO chọn đội cho project."
        actions={
          <Button variant="primary" onClick={() => setCreating(true)}>
            Tạo đội
          </Button>
        }
      />
      <Card>
        <Loaded state={state}>
          {(teams) =>
            teams.length === 0 ? (
              <Empty>Chưa có đội nào.</Empty>
            ) : (
              <Table head={["Đội", "Annotator", "Reviewer", "Trưởng nhóm", "Trạng thái"]}>
                {teams.map((t) => (
                  <tr key={t.id}>
                    <Td>
                      <Link href={`/admin/teams/${t.id}`} className="font-medium underline-offset-2 hover:underline">
                        {t.name}
                      </Link>
                      <span className="ml-2 text-xs text-zinc-500">{t.code}</span>
                    </Td>
                    <Td>{t.annotators}</Td>
                    <Td>{t.reviewers}</Td>
                    <Td>{t.lead?.full_name ?? "—"}</Td>
                    <Td>
                      <Badge>{t.status}</Badge>
                    </Td>
                  </tr>
                ))}
              </Table>
            )
          }
        </Loaded>
      </Card>
      {creating && (
        <Modal title="Tạo đội" onClose={() => setCreating(false)}>
          <form onSubmit={create} className="flex flex-col gap-3">
            {error && <Notice>{error}</Notice>}
            <Field label="Mã đội" hint="Chữ, số, gạch ngang">
              <Input required pattern="[A-Za-z0-9_\-]{2,64}" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />
            </Field>
            <Field label="Tên đội">
              <Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </Field>
            <Field label="Mô tả (tuỳ chọn)">
              <Textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </Field>
            <div className="flex justify-end gap-2">
              <Button onClick={() => setCreating(false)}>Huỷ</Button>
              <Button type="submit" variant="primary">
                Tạo
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
