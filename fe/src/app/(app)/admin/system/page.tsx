"use client";

import { useState } from "react";

import { Badge, Button, Card, Field, Input, Loaded, Notice, PageHeader, Table, Td, useAsync } from "@/components/ui";
import { errorMessage, get, patch } from "@/lib/api";
import type { SettingRow } from "@/lib/types";

type System = {
  settings: SettingRow[];
  parsers: { name: string; version: string; item_type: string; description: string }[];
  item_types: { name: string; description: string }[];
};

export default function SystemPage() {
  const state = useAsync(() => get<System>("/system/settings"));
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<{ tone: "green" | "red"; text: string } | null>(null);

  async function save() {
    setMessage(null);
    const values = Object.fromEntries(Object.entries(edits).map(([k, v]) => [k, Number(v)]));
    try {
      await patch("/system/settings", { values });
      setEdits({});
      await state.reload();
      setMessage({ tone: "green", text: "Đã lưu cài đặt." });
    } catch (e) {
      setMessage({ tone: "red", text: errorMessage(e) });
    }
  }

  return (
    <>
      <PageHeader title="Hệ thống" subtitle="Cài đặt vận hành. Mọi thay đổi được ghi vào audit." />
      <Loaded state={state}>
        {(s) => (
          <div className="flex flex-col gap-6">
            {message && <Notice tone={message.tone}>{message.text}</Notice>}
            <Card
              title="Cài đặt"
              actions={
                <Button variant="primary" disabled={Object.keys(edits).length === 0} onClick={() => void save()}>
                  Lưu
                </Button>
              }
            >
              <div className="grid gap-4 sm:grid-cols-2">
                {s.settings.map((row) => (
                  <Field key={row.key} label={row.label} hint={`Từ ${row.min} đến ${row.max}; mặc định ${row.default}`}>
                    <Input
                      type="number"
                      value={edits[row.key] ?? String(row.value)}
                      onChange={(e) => setEdits({ ...edits, [row.key]: e.target.value })}
                    />
                  </Field>
                ))}
              </div>
            </Card>
            <Card title="Parser có sẵn">
              <Table head={["Tên", "Phiên bản", "Loại item", "Mô tả"]}>
                {s.parsers.map((p) => (
                  <tr key={p.name}>
                    <Td className="font-mono text-xs">{p.name}</Td>
                    <Td>{p.version}</Td>
                    <Td>
                      <Badge tone="blue">{p.item_type}</Badge>
                    </Td>
                    <Td>{p.description}</Td>
                  </tr>
                ))}
              </Table>
              <p className="mt-3 text-xs text-zinc-500">Thêm parser hay loại item mới là thay đổi code và phát hành, không làm qua giao diện.</p>
            </Card>
            <Card title="Loại item">
              <Table head={["Tên", "Mô tả"]}>
                {s.item_types.map((t) => (
                  <tr key={t.name}>
                    <Td className="font-mono text-xs">{t.name}</Td>
                    <Td>{t.description}</Td>
                  </tr>
                ))}
              </Table>
            </Card>
          </div>
        )}
      </Loaded>
    </>
  );
}
