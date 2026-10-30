"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, Suspense, useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { Button, Field, Input, Notice } from "@/components/ui";
import { ApiError, errorMessage } from "@/lib/api";

function LoginForm() {
  const { status, signIn } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (status === "ready") router.replace("/");
  }, [status, router]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(email.trim(), password);
      router.replace("/");
    } catch (err) {
      setError(
        err instanceof ApiError && err.code === "account_inactive"
          ? "Tài khoản đã bị khoá. Liên hệ HR."
          : errorMessage(err, "Không đăng nhập được"),
      );
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      {params.get("expired") && <Notice tone="amber">Phiên đăng nhập đã hết, hãy đăng nhập lại.</Notice>}
      {error && <Notice>{error}</Notice>}
      <Field label="Email">
        <Input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
      </Field>
      <Field label="Mật khẩu">
        <Input
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </Field>
      <Button type="submit" variant="primary" disabled={busy}>
        {busy ? "Đang đăng nhập…" : "Đăng nhập"}
      </Button>
      <p className="text-xs text-zinc-500">
        Tài khoản do HR cấp. Chưa có tài khoản hoặc quên mật khẩu thì liên hệ HR.
      </p>
    </form>
  );
}

export default function LoginPage() {
  return (
    <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center px-6 py-16">
      <h1 className="mb-1 text-2xl font-semibold tracking-tight">Annocollector</h1>
      <p className="mb-8 text-sm text-zinc-500">Đăng nhập để tiếp tục</p>
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </main>
  );
}
