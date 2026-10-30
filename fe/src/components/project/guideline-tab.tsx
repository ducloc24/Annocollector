"use client";

import { useState } from "react";

import {
  Badge,
  Button,
  Card,
  Empty,
  Field,
  formatDate,
  Input,
  Loaded,
  Notice,
  Select,
  Table,
  Td,
  Textarea,
  useAsync,
} from "@/components/ui";
import { errorMessage, get, patch, post } from "@/lib/api";
import type { Guideline, Project, ReasonCode } from "@/lib/types";

const SEVERITY = ["critical", "major", "minor"];
const APPLIES = [
  { value: "label", label: "Annotator chọn" },
  { value: "review", label: "Reviewer ghi" },
  { value: "both", label: "Cả hai" },
];

function ReasonCodes({ project }: { project: Project }) {
  const canEdit = project.my_permissions.includes("project.update");
  const state = useAsync(() => get<ReasonCode[]>(`/projects/${project.id}/reason-codes`), [project.id]);
  const [form, setForm] = useState({ code: "", label: "", default_severity: "major", applies_to: "both" });
  const [error, setError] = useState<string | null>(null);

  async function add() {
    setError(null);
    try {
      await post(`/projects/${project.id}/reason-codes`, form);
      setForm({ code: "", label: "", default_severity: "major", applies_to: "both" });
      await state.reload();
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  async function toggle(rc: ReasonCode) {
    try {
      await patch(`/projects/${project.id}/reason-codes/${rc.id}`, { active: !rc.active });
      await state.reload();
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  return (
    <Card title="Mã lỗi" className="mt-6">
      {error && <div className="mb-3"><Notice>{error}</Notice></div>}
      <Loaded state={state}>
        {(rows) => (
          <Table head={["Mã", "Nhãn", "Mức", "Dùng cho", "", ""]}>
            {rows.map((rc) => (
              <tr key={rc.id} className={rc.active ? "" : "opacity-50"}>
                <Td className="font-mono text-xs">{rc.code}</Td>
                <Td>{rc.label}</Td>
                <Td>
                  <Badge tone={rc.default_severity === "critical" ? "red" : rc.default_severity === "major" ? "amber" : "zinc"}>
                    {rc.default_severity}
                  </Badge>
                </Td>
                <Td>{APPLIES.find((a) => a.value === rc.applies_to)?.label}</Td>
                <Td>{!rc.active && <Badge>đã tắt</Badge>}</Td>
                <Td className="text-right">
                  {canEdit && <Button onClick={() => void toggle(rc)}>{rc.active ? "Tắt" : "Bật"}</Button>}
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Loaded>
      {canEdit && (
        <div className="mt-4 grid gap-3 border-t border-zinc-200 pt-4 dark:border-zinc-800 sm:grid-cols-5">
          <Input placeholder="MA_LOI" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} />
          <Input placeholder="Nhãn hiển thị" value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} />
          <Select value={form.default_severity} onChange={(e) => setForm({ ...form, default_severity: e.target.value })}>
            {SEVERITY.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </Select>
          <Select value={form.applies_to} onChange={(e) => setForm({ ...form, applies_to: e.target.value })}>
            {APPLIES.map((a) => (
              <option key={a.value} value={a.value}>
                {a.label}
              </option>
            ))}
          </Select>
          <Button onClick={() => void add()} disabled={!form.code || !form.label}>
            Thêm mã lỗi
          </Button>
        </div>
      )}
    </Card>
  );
}

export function GuidelineTab({ project }: { project: Project }) {
  const canEdit = project.my_permissions.includes("guideline.manage");
  const list = useAsync(() => get<Guideline[]>(`/projects/${project.id}/guidelines`), [project.id]);
  const [viewing, setViewing] = useState<number | null>(null);
  const [draft, setDraft] = useState<string | null>(null);
  const [diff, setDiff] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const current = useAsync(
    async () => (viewing === null ? null : get<Guideline>(`/projects/${project.id}/guidelines/${viewing}`)),
    [project.id, viewing],
  );

  const latest = list.data?.[0]?.version;

  async function open(version: number) {
    setViewing(version);
    setDraft(null);
    setDiff(null);
  }

  async function startNew() {
    if (latest) {
      const g = await get<Guideline>(`/projects/${project.id}/guidelines/${latest}`);
      setDraft(g.content ?? "");
    } else {
      setDraft("# Guideline\n\nMô tả cách đánh giá đúng/sai và tiêu chí chấm (rubric).\n");
    }
    setViewing(null);
  }

  async function save() {
    setError(null);
    try {
      const g = await post<Guideline>(`/projects/${project.id}/guidelines`, { content: draft });
      setDraft(null);
      await list.reload();
      await open(g.version);
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  async function showDiff(version: number) {
    try {
      setDiff(await get<string>(`/projects/${project.id}/guidelines/${version}/diff?from=${version - 1}`));
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  return (
    <>
      <div className="grid gap-6 lg:grid-cols-[16rem_1fr]">
        <Card
          title="Các version"
          actions={
            canEdit && (
              <Button variant="primary" onClick={() => void startNew()}>
                Version mới
              </Button>
            )
          }
        >
          <Loaded state={list}>
            {(rows) =>
              rows.length === 0 ? (
                <Empty>Chưa có guideline.</Empty>
              ) : (
                <ul className="flex flex-col gap-1">
                  {rows.map((g) => (
                    <li key={g.id}>
                      <button
                        type="button"
                        onClick={() => void open(g.version)}
                        className={`w-full rounded-md px-2 py-1.5 text-left text-sm ${
                          viewing === g.version ? "bg-zinc-100 dark:bg-zinc-900" : "hover:bg-zinc-50 dark:hover:bg-zinc-950"
                        }`}
                      >
                        v{g.version}
                        <span className="block text-xs text-zinc-500">{formatDate(g.created_at)}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )
            }
          </Loaded>
        </Card>

        <Card
          title={draft !== null ? "Soạn version mới" : viewing ? `Version ${viewing}` : "Guideline"}
          actions={
            viewing && viewing > 1 && draft === null ? (
              <Button onClick={() => void showDiff(viewing)}>So với v{viewing - 1}</Button>
            ) : undefined
          }
        >
          {error && <div className="mb-3"><Notice>{error}</Notice></div>}
          {draft !== null ? (
            <div className="flex flex-col gap-3">
              <Field label="Nội dung (Markdown, gồm cả rubric)" hint="Mỗi lần lưu tạo version mới; job đã giao vẫn chấm theo version đã ghim.">
                <Textarea rows={18} className="font-mono" value={draft} onChange={(e) => setDraft(e.target.value)} />
              </Field>
              <div className="flex justify-end gap-2">
                <Button onClick={() => setDraft(null)}>Huỷ</Button>
                <Button variant="primary" disabled={!draft.trim()} onClick={() => void save()}>
                  Lưu thành version mới
                </Button>
              </div>
            </div>
          ) : diff !== null ? (
            <>
              <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-xs">{diff || "Không có thay đổi."}</pre>
              <div className="mt-3">
                <Button onClick={() => setDiff(null)}>Xem nội dung</Button>
              </div>
            </>
          ) : viewing ? (
            <Loaded state={current}>
              {(g) => g && <pre className="whitespace-pre-wrap font-sans text-sm">{g.content}</pre>}
            </Loaded>
          ) : (
            <Empty>Chọn một version để xem.</Empty>
          )}
        </Card>
      </div>
      <ReasonCodes project={project} />
    </>
  );
}
