"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { Button, Card, Field, Input, Notice, PageHeader, Select, Textarea } from "@/components/ui";
import { errorMessage, post } from "@/lib/api";
import type { Project } from "@/lib/types";

export default function NewProjectPage() {
  const router = useRouter();
  const { reload } = useAuth();
  const [form, setForm] = useState({ code: "", name: "", description: "", data_classification: "internal" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const project = await post<Project>("/projects", { ...form, description: form.description || null });
      await reload();
      router.push(`/projects/${project.id}`);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="Tạo project" subtitle="Bạn sẽ là owner. Sau đó làm theo checklist thiết lập." />
      <div className="max-w-xl">
        <Card>
          <form onSubmit={submit} className="flex flex-col gap-4">
            {error && <Notice>{error}</Notice>}
            <Field label="Mã project" hint="Chữ, số, gạch ngang; không đổi được">
              <Input required pattern="[A-Za-z0-9_\-]{2,64}" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />
            </Field>
            <Field label="Tên project">
              <Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </Field>
            <Field label="Mô tả (tuỳ chọn)">
              <Textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </Field>
            <Field label="Mức phân loại dữ liệu">
              <Select value={form.data_classification} onChange={(e) => setForm({ ...form, data_classification: e.target.value })}>
                <option value="internal">Nội bộ</option>
                <option value="confidential">Bảo mật</option>
                <option value="restricted">Hạn chế</option>
              </Select>
            </Field>
            <div className="flex justify-end">
              <Button type="submit" variant="primary" disabled={busy}>
                Tạo project
              </Button>
            </div>
          </form>
        </Card>
      </div>
    </>
  );
}
