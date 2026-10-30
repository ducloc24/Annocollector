"use client";

import { useState } from "react";

import { StepsView } from "@/components/step-view";
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
  Table,
  Td,
  useAsync,
} from "@/components/ui";
import { ApiError, errorMessage, get, post, request } from "@/lib/api";
import type { Dataset, ItemPayload, ParseReport, Project } from "@/lib/types";

type Parser = { name: string; version: string; item_type: string; description: string; default_options: Record<string, string> };
type Preview = {
  items: { ordinal: number; external_ref: string | null; payload: ItemPayload }[];
  report: ParseReport;
};
type Upload = { upload_key: string; url: string };

const OPTION_LABELS: Record<string, string> = {
  id: "Mã bản ghi",
  user_message: "Yêu cầu của user",
  tools: "Danh sách tool",
  steps: "Các bước",
  step_type: "Loại bước",
  step_content: "Nội dung bước",
  tool_name: "Tên tool",
  tool_args: "Tham số tool",
};

function Report({ report }: { report: ParseReport }) {
  return (
    <div className="flex flex-col gap-2 text-sm">
      <p>
        {report.lines_ok}/{report.lines_total} dòng đọc được
        {report.error_count > 0 && <span className="text-red-600"> · {report.error_count} lỗi</span>}
      </p>
      {report.errors.length > 0 && (
        <ul className="max-h-40 overflow-y-auto rounded-md bg-zinc-50 p-2 font-mono text-xs dark:bg-zinc-950">
          {report.errors.map((e, i) => (
            <li key={i}>
              dòng {e.line}: {e.code}: {e.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Wizard({ project, onClose, onDone }: { project: Project; onClose: () => void; onDone: () => void }) {
  const parsers = useAsync(() => get<Parser[]>("/parsers"));
  const [file, setFile] = useState<File | null>(null);
  const [upload, setUpload] = useState<Upload | null>(null);
  const [options, setOptions] = useState<Record<string, string>>({});
  const parser = "jsonl_chat";
  const [preview, setPreview] = useState<Preview | null>(null);
  const [report, setReport] = useState<ParseReport | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const defaults = parsers.data?.find((p) => p.name === parser)?.default_options ?? {};
  const merged = { ...defaults, ...options };

  async function send() {
    if (!file) return;
    setBusy("Đang tải file lên…");
    setError(null);
    try {
      const target = await post<Upload>(`/projects/${project.id}/datasets/upload-url`, {
        filename: file.name,
        size: file.size,
      });
      const response = await fetch(target.url, {
        method: "PUT",
        body: file,
        headers: { "Content-Type": "application/octet-stream" },
      });
      if (!response.ok) throw new Error("Không tải được file lên kho lưu trữ");
      setUpload(target);
      await runPreview(target);
    } catch (e) {
      setError(errorMessage(e, e instanceof Error ? e.message : undefined));
    } finally {
      setBusy(null);
    }
  }

  async function runPreview(target = upload) {
    if (!target) return;
    setBusy("Đang đọc thử…");
    setError(null);
    try {
      setPreview(
        await post<Preview>(`/projects/${project.id}/datasets/preview`, {
          upload_key: target.upload_key,
          parser,
          parser_options: options,
        }),
      );
    } catch (e) {
      setPreview(null);
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  async function create() {
    if (!upload) return;
    setBusy("Đang tạo version…");
    setError(null);
    try {
      await request(`/projects/${project.id}/datasets`, {
        method: "POST",
        body: JSON.stringify({ upload_key: upload.upload_key, parser, parser_options: options }),
      });
      onDone();
      onClose();
    } catch (e) {
      if (e instanceof ApiError && e.code === "parse_failed") {
        setReport((e.details as { parse_report: ParseReport } | undefined)?.parse_report ?? null);
      }
      setError(errorMessage(e));
      setBusy(null);
    }
  }

  return (
    <Modal title="Thêm dataset version" onClose={onClose}>
      <div className="flex flex-col gap-4">
        {error && <Notice>{error}</Notice>}
        {report && <Report report={report} />}
        <Field label="File JSONL" hint="Mỗi dòng là một trajectory của agent. Xem be/samples/trajectories.jsonl.">
          <Input type="file" accept=".jsonl,.json,.txt" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setUpload(null); setPreview(null); }} />
        </Field>
        {!upload && (
          <Button variant="primary" disabled={!file || !!busy} onClick={() => void send()}>
            {busy ?? "Tải lên và đọc thử"}
          </Button>
        )}
        {upload && (
          <>
            <details className="rounded-md border border-zinc-200 p-3 text-sm dark:border-zinc-800">
              <summary className="cursor-pointer font-medium">Ánh xạ trường (JSONPath)</summary>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                {Object.keys(defaults).map((key) => (
                  <Field key={key} label={OPTION_LABELS[key] ?? key}>
                    <Input
                      className="font-mono text-xs"
                      value={merged[key]}
                      onChange={(e) => setOptions({ ...options, [key]: e.target.value })}
                    />
                  </Field>
                ))}
              </div>
              <div className="mt-3">
                <Button disabled={!!busy} onClick={() => void runPreview()}>
                  Đọc thử lại
                </Button>
              </div>
            </details>
            {preview && (
              <div className="flex flex-col gap-3">
                <Report report={preview.report} />
                {preview.items.slice(0, 2).map((item) => (
                  <div key={item.ordinal} className="rounded-md border border-zinc-200 p-3 dark:border-zinc-800">
                    <p className="mb-2 text-xs text-zinc-500">
                      Item {item.ordinal} · {item.payload.targets.length} tool call cần đánh giá
                    </p>
                    <StepsView steps={item.payload.steps} compact />
                  </div>
                ))}
              </div>
            )}
            <div className="flex justify-end gap-2">
              <Button onClick={onClose}>Huỷ</Button>
              <Button
                variant="primary"
                disabled={!preview || preview.items.length === 0 || !!busy}
                onClick={() => void create()}
              >
                {busy ?? "Tạo version"}
              </Button>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}

export function DataTab({ project }: { project: Project }) {
  const state = useAsync(() => get<Dataset[]>(`/projects/${project.id}/datasets`), [project.id]);
  const [adding, setAdding] = useState(false);
  const [viewing, setViewing] = useState<Dataset | null>(null);

  return (
    <>
      <Card
        title="Dataset version"
        actions={
          <Button variant="primary" onClick={() => setAdding(true)}>
            Thêm version
          </Button>
        }
      >
        <Loaded state={state}>
          {(rows) =>
            rows.length === 0 ? (
              <Empty>Chưa có dữ liệu. Thêm version đầu tiên bằng file JSONL.</Empty>
            ) : (
              <Table head={["Version", "Item", "Loại", "Parser", "Tạo lúc", ""]}>
                {rows.map((d) => (
                  <tr key={d.id}>
                    <Td>v{d.version}</Td>
                    <Td>{d.item_count}</Td>
                    <Td>
                      <Badge tone="blue">{d.item_type}</Badge>
                    </Td>
                    <Td className="text-xs">
                      {d.parser} {d.parser_version}
                    </Td>
                    <Td>{formatDate(d.created_at)}</Td>
                    <Td className="text-right">
                      <Button variant="ghost" onClick={() => setViewing(d)}>
                        Báo cáo
                      </Button>
                    </Td>
                  </tr>
                ))}
              </Table>
            )
          }
        </Loaded>
      </Card>
      {adding && <Wizard project={project} onClose={() => setAdding(false)} onDone={() => void state.reload()} />}
      {viewing && (
        <Modal title={`Dataset v${viewing.version}`} onClose={() => setViewing(null)}>
          <div className="flex flex-col gap-3 text-sm">
            <Report report={viewing.parse_report} />
            <p className="break-all font-mono text-xs text-zinc-500">{viewing.checksum}</p>
            <pre className="overflow-x-auto rounded-md bg-zinc-50 p-2 font-mono text-xs dark:bg-zinc-950">
              {JSON.stringify(viewing.parser_options, null, 2)}
            </pre>
          </div>
        </Modal>
      )}
    </>
  );
}
