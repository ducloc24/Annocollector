"use client";

import { useState } from "react";

import { LabelForm } from "@/components/label-form";
import {
  Badge,
  Button,
  Card,
  Empty,
  Field,
  formatDate,
  Input,
  Loaded,
  Modal,
  Notice,
  Select,
  Table,
  Td,
  Textarea,
  useAsync,
} from "@/components/ui";
import { errorMessage, get, post } from "@/lib/api";
import type { FieldDef, JobConfig, LabelSchema, LabelValue, Project, ReasonCode } from "@/lib/types";

type ItemType = { name: string; description: string; field_types: string[]; default_label_schema: LabelSchema | null };

const RULE_FIELDS: { key: string; label: string; hint: string }[] = [
  { key: "items_per_job", label: "Số item mỗi job", hint: "Với tool call: số trajectory mỗi job" },
  { key: "max_rework", label: "Số lần sửa tối đa", hint: "Vượt quá thì job được escalate" },
  { key: "lease_minutes", label: "Thời gian giữ job (phút)", hint: "Hết hạn thì job về hàng đợi" },
  { key: "wip_limit_annotator", label: "Giới hạn job đang làm / annotator", hint: "" },
  { key: "wip_limit_reviewer", label: "Giới hạn job đang chấm / reviewer", hint: "" },
  { key: "review_sla_hours", label: "SLA chấm (giờ)", hint: "Quá hạn thì tính là kẹt" },
  { key: "review_rate", label: "Tỷ lệ review (0.05–1)", hint: "1 = chấm mọi job; nhỏ hơn thì job không được chọn tự động được chấp nhận. Job không chắc, job sửa lại và gold job luôn được chấm." },
];

function emptyField(): FieldDef {
  return { name: "", label: "", type: "text", required: false };
}

function FieldEditor({ field, onChange, onRemove }: { field: FieldDef; onChange: (f: FieldDef) => void; onRemove: () => void }) {
  const hasOptions = field.type === "enum" || field.type === "multi_select";
  return (
    <div className="rounded-md border border-zinc-200 p-3 dark:border-zinc-800">
      <div className="grid gap-3 sm:grid-cols-4">
        <Field label="Tên trường">
          <Input className="font-mono text-xs" value={field.name} onChange={(e) => onChange({ ...field, name: e.target.value })} />
        </Field>
        <Field label="Nhãn hiển thị">
          <Input value={field.label ?? ""} onChange={(e) => onChange({ ...field, label: e.target.value })} />
        </Field>
        <Field label="Kiểu">
          <Select value={field.type} onChange={(e) => onChange({ ...field, type: e.target.value as FieldDef["type"] })}>
            <option value="enum">Chọn một</option>
            <option value="multi_select">Chọn nhiều</option>
            <option value="text">Văn bản</option>
            <option value="number">Số</option>
            <option value="boolean">Có/không</option>
          </Select>
        </Field>
        <label className="flex items-end gap-2 pb-2 text-sm">
          <input type="checkbox" checked={!!field.required} onChange={(e) => onChange({ ...field, required: e.target.checked })} />
          Bắt buộc
        </label>
      </div>
      {hasOptions && (
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <Field label="Nguồn lựa chọn">
            <Select
              value={field.options_from ?? ""}
              onChange={(e) => onChange({ ...field, options_from: e.target.value || undefined })}
            >
              <option value="">Tự nhập bên dưới</option>
              <option value="reason_codes">Mã lỗi của project</option>
            </Select>
          </Field>
          {!field.options_from && (
            <Field label="Các lựa chọn" hint="Phân cách bằng dấu phẩy">
              <Input
                value={(field.options ?? []).join(", ")}
                onChange={(e) =>
                  onChange({ ...field, options: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })
                }
              />
            </Field>
          )}
        </div>
      )}
      <div className="mt-3 grid items-end gap-3 sm:grid-cols-3">
        <Field label="Chỉ hiện khi trường" hint="Để trống nếu luôn hiện">
          <Input
            className="font-mono text-xs"
            value={field.visible_if?.field ?? ""}
            onChange={(e) =>
              onChange({ ...field, visible_if: e.target.value ? { field: e.target.value, equals: field.visible_if?.equals ?? "" } : undefined })
            }
          />
        </Field>
        <Field label="…có giá trị">
          <Input
            disabled={!field.visible_if}
            value={String(field.visible_if?.equals ?? "")}
            onChange={(e) => field.visible_if && onChange({ ...field, visible_if: { ...field.visible_if, equals: e.target.value } })}
          />
        </Field>
        <div className="text-right">
          <Button variant="danger" onClick={onRemove}>
            Xoá trường
          </Button>
        </div>
      </div>
    </div>
  );
}

function Editor({ project, base, onClose, onDone }: { project: Project; base: JobConfig | null; onClose: () => void; onDone: () => void }) {
  const types = useAsync(() => get<ItemType[]>("/item-types"));
  const codes = useAsync(() => get<ReasonCode[]>(`/projects/${project.id}/reason-codes`), [project.id]);
  const defaultSchema = types.data?.[0]?.default_label_schema;
  const [schema, setSchema] = useState<LabelSchema | null>(base?.label_schema ?? null);
  const [rules, setRules] = useState<Record<string, number | string>>(base?.job_rules ?? {});
  const [selfCheck, setSelfCheck] = useState((base?.self_check ?? []).join("\n"));
  const [mode, setMode] = useState<"pull" | "push_only">((base?.job_rules.assignment_mode as "pull") ?? "pull");
  const [preview, setPreview] = useState<LabelValue>({});
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const effective = schema ?? defaultSchema ?? null;
  const questions = selfCheck.split("\n").map((s) => s.trim()).filter(Boolean);
  const payload = () => ({
    item_type: "tool_call",
    label_schema: effective,
    job_rules: { ...rules, assignment_mode: mode },
    self_check: questions,
  });

  async function check() {
    try {
      const result = await post<{ valid: boolean; errors: string[] }>(`/projects/${project.id}/job-configs/validate`, payload());
      setErrors(result.errors);
      return result.valid;
    } catch (e) {
      setErrors([errorMessage(e)]);
      return false;
    }
  }

  async function save() {
    setBusy(true);
    if (await check()) {
      try {
        await post(`/projects/${project.id}/job-configs`, payload());
        onDone();
        onClose();
        return;
      } catch (e) {
        setErrors([errorMessage(e)]);
      }
    }
    setBusy(false);
  }

  if (!effective) return <Modal title="Cấu hình job" onClose={onClose}><p className="text-sm">Đang tải…</p></Modal>;

  return (
    <Modal title={base ? `Version mới (dựa trên v${base.version})` : "Cấu hình job đầu tiên"} onClose={onClose}>
      <div className="flex flex-col gap-5">
        {errors.length > 0 && (
          <Notice>
            <ul className="list-disc pl-4">
              {errors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          </Notice>
        )}
        <section className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold">Các trường nhãn (label schema)</h3>
          {effective.fields.map((f, i) => (
            <FieldEditor
              key={i}
              field={f}
              onChange={(next) => setSchema({ ...effective, fields: effective.fields.map((x, j) => (j === i ? next : x)) })}
              onRemove={() => setSchema({ ...effective, fields: effective.fields.filter((_, j) => j !== i) })}
            />
          ))}
          <div>
            <Button onClick={() => setSchema({ ...effective, fields: [...effective.fields, emptyField()] })}>Thêm trường</Button>
          </div>
        </section>

        <section className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold">Quy tắc job</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            {RULE_FIELDS.map((r) => (
              <Field key={r.key} label={r.label} hint={r.hint || undefined}>
                <Input
                  type="number"
                  step="any"
                  placeholder="mặc định"
                  value={rules[r.key] ?? ""}
                  onChange={(e) => {
                    const next = { ...rules };
                    if (e.target.value === "") delete next[r.key];
                    else next[r.key] = Number(e.target.value);
                    setRules(next);
                  }}
                />
              </Field>
            ))}
            <Field label="Cách giao việc">
              <Select value={mode} onChange={(e) => setMode(e.target.value as "pull" | "push_only")}>
                <option value="pull">Thành viên tự lấy việc (khuyên dùng)</option>
                <option value="push_only">Chỉ PM giao tay</option>
              </Select>
            </Field>
          </div>
        </section>

        <section>
          <Field label="Câu hỏi self-check (mỗi dòng một câu)" hint="Annotator phải tick hết trước khi nộp">
            <Textarea rows={3} value={selfCheck} onChange={(e) => setSelfCheck(e.target.value)} />
          </Field>
        </section>

        <section className="rounded-md border border-dashed border-zinc-300 p-3 dark:border-zinc-700">
          <h3 className="mb-3 text-sm font-semibold">Xem trước form gán nhãn</h3>
          <LabelForm
            schema={effective}
            value={preview}
            onChange={setPreview}
            codes={(codes.data ?? []).filter((c) => c.active && c.applies_to !== "review")}
          />
        </section>

        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Huỷ</Button>
          <Button onClick={() => void check()}>Kiểm tra</Button>
          <Button variant="primary" disabled={busy} onClick={() => void save()}>
            Lưu thành version mới
          </Button>
        </div>
        <p className="text-xs text-zinc-500">Version đã lưu không sửa được; job đã giao giữ cấu hình cũ.</p>
      </div>
    </Modal>
  );
}

export function ConfigTab({ project }: { project: Project }) {
  const state = useAsync(() => get<JobConfig[]>(`/projects/${project.id}/job-configs`), [project.id]);
  const [editing, setEditing] = useState<{ base: JobConfig | null } | null>(null);
  const [viewing, setViewing] = useState<JobConfig | null>(null);

  return (
    <>
      <Card
        title="Cấu hình job"
        actions={
          <Button variant="primary" onClick={() => setEditing({ base: state.data?.[0] ?? null })}>
            Version mới
          </Button>
        }
      >
        <p className="mb-4 text-sm text-zinc-500">
          Quy định thế nào là một job: các trường nhãn, số item mỗi job, giới hạn, câu hỏi self-check.
        </p>
        <Loaded state={state}>
          {(rows) =>
            rows.length === 0 ? (
              <Empty>Chưa có cấu hình nào.</Empty>
            ) : (
              <Table head={["Version", "Loại item", "Trường nhãn", "Item/job", "Tạo lúc", ""]}>
                {rows.map((c) => (
                  <tr key={c.id}>
                    <Td>v{c.version}</Td>
                    <Td>
                      <Badge tone="blue">{c.item_type}</Badge>
                    </Td>
                    <Td className="text-xs">{c.label_schema.fields.map((f) => f.name).join(", ")}</Td>
                    <Td>{c.job_rules.items_per_job}</Td>
                    <Td>{formatDate(c.created_at)}</Td>
                    <Td className="text-right">
                      <Button variant="ghost" onClick={() => setViewing(c)}>
                        Xem
                      </Button>
                    </Td>
                  </tr>
                ))}
              </Table>
            )
          }
        </Loaded>
      </Card>
      {editing && <Editor project={project} base={editing.base} onClose={() => setEditing(null)} onDone={() => void state.reload()} />}
      {viewing && (
        <Modal title={`Cấu hình v${viewing.version}`} onClose={() => setViewing(null)}>
          <pre className="overflow-x-auto font-mono text-xs">
            {JSON.stringify({ label_schema: viewing.label_schema, job_rules: viewing.job_rules, self_check: viewing.self_check }, null, 2)}
          </pre>
        </Modal>
      )}
    </>
  );
}
