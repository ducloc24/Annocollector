"use client";

import { useRouter } from "next/navigation";
import {
  type ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  get,
  login as apiLogin,
  logout as apiLogout,
  refreshSession,
  setAccessToken,
  setSessionLostHandler,
} from "@/lib/api";
import type { MyTeam, Project, User } from "@/lib/types";

type Status = "loading" | "anonymous" | "ready";

type AuthState = {
  status: Status;
  user: User | null;
  permissions: Record<string, string[]>;
  teams: MyTeam[];
  projects: Project[];
  can: (permission: string) => boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  reload: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [status, setStatus] = useState<Status>("loading");
  const [user, setUser] = useState<User | null>(null);
  const [permissions, setPermissions] = useState<Record<string, string[]>>({});
  const [teams, setTeams] = useState<MyTeam[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);

  const load = useCallback(async () => {
    const [me, perms, myTeams, myProjects] = await Promise.all([
      get<User>("/me"),
      get<{ permissions: Record<string, string[]> }>("/me/permissions"),
      get<MyTeam[]>("/me/teams"),
      get<Project[]>("/projects"),
    ]);
    setUser(me);
    setPermissions(perms.permissions);
    setTeams(myTeams);
    setProjects(myProjects);
    setStatus("ready");
  }, []);

  const clear = useCallback(() => {
    setAccessToken(null);
    setUser(null);
    setPermissions({});
    setTeams([]);
    setProjects([]);
    setStatus("anonymous");
  }, []);

  useEffect(() => {
    setSessionLostHandler(() => {
      clear();
      router.replace("/login?expired=1");
    });
    let cancelled = false;
    (async () => {
      if (await refreshSession()) {
        try {
          await load();
        } catch {
          if (!cancelled) clear();
        }
      } else if (!cancelled) {
        clear();
      }
    })();
    return () => {
      cancelled = true;
      setSessionLostHandler(null);
    };
  }, [clear, load, router]);

  const signIn = useCallback(
    async (email: string, password: string) => {
      await apiLogin(email, password);
      await load();
    },
    [load],
  );

  const signOut = useCallback(async () => {
    await apiLogout();
    clear();
    router.replace("/login");
  }, [clear, router]);

  const value = useMemo<AuthState>(
    () => ({
      status,
      user,
      permissions,
      teams,
      projects,
      can: (permission) => permission in permissions,
      signIn,
      signOut,
      reload: load,
    }),
    [status, user, permissions, teams, projects, signIn, signOut, load],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/** Renders children only for a signed-in user; otherwise sends them to /login. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (status === "anonymous") router.replace("/login");
  }, [status, router]);
  if (status !== "ready") {
    return <p className="p-10 text-center text-sm text-zinc-500">Đang tải…</p>;
  }
  return <>{children}</>;
}
