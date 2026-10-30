"use client";

import { RequireAuth } from "@/components/auth-provider";

/** Work screens fill the page: no sidebar, only a way back. */
export default function WorkLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <div className="flex h-screen flex-col">{children}</div>
    </RequireAuth>
  );
}
