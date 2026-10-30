"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { type FormEvent, Suspense, useState } from "react";

import { Button, Field, Input, Notice } from "@/components/ui";
import { errorMessage, post } from "@/lib/api";

function ActivateForm() {
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (password !== repeat) {
      setError("Hai mật khẩu không khớp");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await post("/auth/activate", { token, password });
      setDone(true);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  if (!token) {
    return <Notice>Link kích hoạt không hợp lệ. Liên hệ HR để được cấp link mới.</Notice>;
  }
  if (done) {
    return (
      <div className="flex flex-col gap-4">
        <Notice tone="green">Đã đặt mật khẩu. Bạn có thể đăng nhập.</Notice>
        <Link href="/login" className="text-sm underline underline-offset-2">
          Đến trang đăng nhập
        </Link>
      </div>
    );
  }
  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      {error && <Notice>{error}</Notice>}
      <Field label="Mật khẩu mới" hint="Tối thiểu 10 ký tự">
        <Input type="password" autoComplete="new-password" minLength={10} required value={password} onChange={(e) => setPassword(e.target.value)} />
      </Field>
      <Field label="Nhập lại mật khẩu">
        <Input type="password" autoComplete="new-password" required value={repeat} onChange={(e) => setRepeat(e.target.value)} />
      </Field>
      <Button type="submit" variant="primary" disabled={busy}>
        Kích hoạt tài khoản
      </Button>
    </form>
  );
}

export default function ActivatePage() {
  return (
    <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center px-6 py-16">
      <h1 className="mb-1 text-2xl font-semibold tracking-tight">Kích hoạt tài khoản</h1>
      <p className="mb-8 text-sm text-zinc-500">Đặt mật khẩu để bắt đầu sử dụng.</p>
      <Suspense fallback={null}>
        <ActivateForm />
      </Suspense>
    </main>
  );
}
