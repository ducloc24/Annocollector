"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { type ReactNode } from "react";

import { RequireAuth, useAuth } from "@/components/auth-provider";

type NavItem = { href: string; label: string; show: boolean };

function Shell({ children }: { children: ReactNode }) {
  const { user, can, teams, projects, signOut } = useAuth();
  const pathname = usePathname();

  const isAnnotator = teams.some((t) => t.team_role === "annotator");
  const isReviewer = teams.some((t) => t.team_role === "reviewer");
  const leadTeam = teams.find((t) => t.is_lead);
  const isLead = !!leadTeam;

  const sections: { title?: string; items: NavItem[] }[] = [
    {
      items: [
        { href: "/", label: "Việc cần làm", show: true },
        { href: "/work", label: "Gán nhãn", show: isAnnotator },
        { href: "/review", label: "Chấm", show: isReviewer },
        { href: leadTeam ? `/teams/${leadTeam.team_id}` : "/teams", label: "Đội của tôi", show: isLead },
        {
          href: "/projects",
          label: "Project",
          show: can("project.create") || projects.length > 0,
        },
      ],
    },
    {
      title: "Quản trị",
      items: [
        { href: "/admin/users", label: "Người dùng", show: can("user.manage") },
        { href: "/admin/teams", label: "Đội đánh giá", show: can("team.manage") },
        {
          href: "/admin/roles/expiring",
          label: "Quyền sắp hết hạn",
          show: can("platform_role.grant"),
        },
        { href: "/admin/audit", label: "Audit", show: can("audit.read") },
        { href: "/admin/system", label: "Hệ thống", show: can("system.configure") },
      ],
    },
    {
      items: [{ href: "/account", label: "Tài khoản", show: true }],
    },
  ];

  const active = (href: string) =>
    href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);

  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-56 shrink-0 flex-col border-r border-zinc-200 p-4 dark:border-zinc-800 md:flex">
        <Link href="/" className="mb-6 text-lg font-semibold tracking-tight">
          Annocollector
        </Link>
        <nav className="flex flex-1 flex-col gap-5">
          {sections.map((section, i) => {
            const items = section.items.filter((n) => n.show);
            if (items.length === 0) return null;
            return (
              <div key={i} className="flex flex-col gap-1">
                {section.title && (
                  <p className="px-2 text-xs font-medium uppercase tracking-wide text-zinc-500">
                    {section.title}
                  </p>
                )}
                {items.map((n) => (
                  <Link
                    key={n.href}
                    href={n.href}
                    className={`rounded-md px-2 py-1.5 text-sm ${
                      active(n.href)
                        ? "bg-zinc-100 font-medium dark:bg-zinc-900"
                        : "text-zinc-600 hover:bg-zinc-50 dark:text-zinc-400 dark:hover:bg-zinc-950"
                    }`}
                  >
                    {n.label}
                  </Link>
                ))}
              </div>
            );
          })}
        </nav>
        <div className="border-t border-zinc-200 pt-3 text-sm dark:border-zinc-800">
          <p className="truncate font-medium">{user?.full_name}</p>
          {isLead && <p className="text-xs text-zinc-500">Trưởng nhóm</p>}
          <button
            type="button"
            onClick={() => void signOut()}
            className="mt-1 text-xs text-zinc-500 underline underline-offset-2 hover:text-zinc-900 dark:hover:text-zinc-100"
          >
            Đăng xuất
          </button>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-zinc-200 px-4 py-3 dark:border-zinc-800 md:hidden">
          <Link href="/" className="font-semibold">
            Annocollector
          </Link>
          <Link href="/account" className="text-sm text-zinc-500">
            {user?.full_name}
          </Link>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-5 py-8">{children}</main>
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <RequireAuth>
      <Shell>{children}</Shell>
    </RequireAuth>
  );
}
