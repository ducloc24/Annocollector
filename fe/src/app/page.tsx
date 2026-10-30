import Link from "next/link";

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-10 px-6 py-16">
      <header className="flex flex-col gap-3">
        <span className="w-fit rounded-full border border-zinc-200 px-3 py-1 text-xs font-medium text-zinc-500 dark:border-zinc-800">
          Annocollector
        </span>
        <h1 className="text-3xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
          Annotation platform
        </h1>
        <p className="max-w-xl text-sm leading-6 text-zinc-600 dark:text-zinc-400">
          Nền tảng gán nhãn nội bộ. Thiết kế nằm trong <code className="font-mono">docs/</code>.
        </p>
        <div className="flex flex-wrap gap-3 text-sm">
          <Link
            className="font-medium text-zinc-900 underline underline-offset-4 dark:text-zinc-100"
            href="/demo/annotate"
          >
            Demo màn hình gán nhãn
          </Link>
          <a
            className="font-medium text-zinc-900 underline underline-offset-4 dark:text-zinc-100"
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noreferrer"
          >
            API docs
          </a>
        </div>
      </header>
    </main>
  );
}
