"use client";

import { useState } from "react";

import {
  Badge,
  Button,
  Card,
  Empty,
  Field,
  formatDate,
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
import type { Appeal, JobView, Project } from "@/lib/types";

const STATUS: Record<string, string> = { open: "Chờ PM", po_decision: "Chờ owner", closed: "Đã đóng" };
const OUTCOME: Record<string, string> = { upheld: "Giữ nguyên quyết định", overturned: "Đã đảo quyết định" };

function Decide({ project, appeal, onClose, onDone }: { project: Project; appeal: Appeal; onClose: () => void; onDone: () => void }) {
  const isOwner = project.my_roles.includes("owner");
  const job = useAsync(() => get<JobView>(`/jobs/${appeal.job_id}`), [appeal.job_id]);
  const [action, setAction] = useState<"upheld" | "overturned" | "forward">("overturned");
  const [resolution, setResolution] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    try {
      await post(`/projects/${project.id}/appeals/${appeal.id}/decision`, { action, resolution });
      onDone();
      onClose();
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  return (
    <Modal title={`Khiếu nại · job #${appeal.job_ordinal}`} onClose={onClose}>
      <div className="flex flex-col gap-4 text-sm">
        {error && <Notice>{error}</Notice>}
        <div className="rounded-md bg-zinc-50 p-3 dark:bg-zinc-950">
          <p className="font-medium">{appeal.opener_name} viết:</p>
          <p className="whitespace-pre-wrap">{appeal.reason}</p>
        </div>
        <Loaded state={job}>
          {(v) => (
            <div className="flex flex-col gap-2">
              <p className="text-zinc-500">Chấm theo guideline v{v.guideline.version} (đã ghim lúc giao job).</p>
              {v.rounds?.map((r) => (
                <div key={r.round} className="rounded-md border border-zinc-200 p-3 dark:border-zinc-800">
                  <p className="font-medium">Lượt {r.round}</p>
                  {r.review ? (
                    <>
                      <p>
                        Quyết định: <Badge>{r.review.decision}</Badge> {r.review.reason}
                      </p>
                      <ul className="mt-1 list-disc pl-5 text-xs">
                        {r.review.errors.map((e, i) => (
                          <li key={i}>
                            {e.target}: {e.reason_code} ({e.severity}) {e.note}
                          </li>
                        ))}
                      </ul>
                    </>
                  ) : (
                    <p className="text-zinc-500">Chưa có review.</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </Loaded>
        <Field label="Quyết định">
          <Select value={action} onChange={(e) => setAction(e.target.value as typeof action)}>
            <option value="overturned">Annotator đúng: chấp nhận job</option>
            <option value="upheld">Giữ nguyên quyết định trả lại</option>
            {appeal.status === "open" && !isOwner && <option value="forward">Chuyển lên owner quyết</option>}
            {appeal.status === "open" && isOwner && <option value="forward">Chuyển bước owner (không cần)</option>}
          </Select>
        </Field>
        <Field label="Lý do (bắt buộc)">
          <Textarea rows={3} value={resolution} onChange={(e) => setResolution(e.target.value)} />
        </Field>
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Huỷ</Button>
          <Button variant="primary" disabled={resolution.trim().length < 3} onClick={() => void submit()}>
            Lưu quyết định
          </Button>
        </div>
      </div>
    </Modal>
  );
}

export function AppealsTab({ project }: { project: Project }) {
  const state = useAsync(() => get<Appeal[]>(`/projects/${project.id}/appeals`), [project.id]);
  const [open, setOpen] = useState<Appeal | null>(null);

  return (
    <>
      <Card title="Khiếu nại của annotator">
        <p className="mb-4 text-sm text-zinc-500">
          PM xem bước 1 và có thể chuyển lên owner. Quyết định cuối được lưu bất biến kèm lý do.
        </p>
        <Loaded state={state}>
          {(rows) =>
            rows.length === 0 ? (
              <Empty>Chưa có khiếu nại nào.</Empty>
            ) : (
              <Table head={["Job", "Người khiếu nại", "Trạng thái", "Kết quả", "Mở lúc", ""]}>
                {rows.map((a) => (
                  <tr key={a.id}>
                    <Td>#{a.job_ordinal}</Td>
                    <Td>{a.opener_name}</Td>
                    <Td>
                      <Badge tone={a.status === "closed" ? "zinc" : "amber"}>{STATUS[a.status]}</Badge>
                    </Td>
                    <Td>{a.outcome ? OUTCOME[a.outcome] : "—"}</Td>
                    <Td>{formatDate(a.opened_at)}</Td>
                    <Td className="text-right">
                      {a.status !== "closed" && (
                        <Button variant="primary" onClick={() => setOpen(a)}>
                          Xem và quyết định
                        </Button>
                      )}
                    </Td>
                  </tr>
                ))}
              </Table>
            )
          }
        </Loaded>
      </Card>
      {open && <Decide project={project} appeal={open} onClose={() => setOpen(null)} onDone={() => void state.reload()} />}
    </>
  );
}
