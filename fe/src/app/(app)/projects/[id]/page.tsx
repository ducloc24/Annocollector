"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { useAuth } from "@/components/auth-provider";
import { ConfigTab } from "@/components/project/config-tab";
import { DataTab } from "@/components/project/data-tab";
import { GuidelineTab } from "@/components/project/guideline-tab";
import { JobsTab } from "@/components/project/jobs-tab";
import { OverviewTab } from "@/components/project/overview-tab";
import { PeopleTab } from "@/components/project/people-tab";
import { TasksTab } from "@/components/project/tasks-tab";
import { Badge, Loaded, PageHeader, Tabs, useAsync } from "@/components/ui";
import { get } from "@/lib/api";
import type { Project } from "@/lib/types";

function Workspace() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const params = useSearchParams();
  const { reload: reloadAuth } = useAuth();
  const state = useAsync(() => get<Project>(`/projects/${id}`), [id]);

  return (
    <Loaded state={state}>
      {(project) => {
        const has = (perm: string) => project.my_permissions.includes(perm);
        const tabs = [
          { id: "overview", label: "Tổng quan", show: true },
          { id: "people", label: "Thành viên và đội", show: has("member.manage") || has("project.update") },
          { id: "guideline", label: "Guideline", show: has("guideline.manage") || has("progress.read") },
          { id: "data", label: "Dữ liệu", show: has("dataset.upload") },
          { id: "config", label: "Cấu hình job", show: has("job_config.manage") },
          { id: "tasks", label: "Task", show: has("task.manage") || has("task.accept") },
          { id: "jobs", label: "Job", show: has("job.assign") },
          { id: "escalations", label: "Escalation", show: has("appeal.decide") },
        ].filter((t) => t.show);
        const requested = params.get("tab") ?? "overview";
        const active = tabs.some((t) => t.id === requested) ? requested : "overview";
        const refresh = async () => {
          await state.reload();
          await reloadAuth();
        };

        return (
          <>
            <PageHeader
              title={
                <>
                  {project.name} <Badge>{project.status}</Badge>
                </>
              }
              subtitle={`${project.code} · bạn là ${project.my_roles.join(", ")}`}
              actions={
                <Link href="/projects" className="text-sm underline underline-offset-2">
                  ← Project
                </Link>
              }
            />
            <Tabs
              tabs={tabs}
              active={active}
              onChange={(tab) => router.replace(`/projects/${id}?tab=${tab}`)}
            />
            {active === "overview" && <OverviewTab project={project} onChange={refresh} />}
            {active === "people" && <PeopleTab project={project} />}
            {active === "guideline" && <GuidelineTab project={project} />}
            {active === "data" && <DataTab project={project} />}
            {active === "config" && <ConfigTab project={project} />}
            {active === "tasks" && <TasksTab project={project} />}
            {active === "jobs" && <JobsTab project={project} mode="jobs" stuck={params.get("stuck") === "1"} />}
            {active === "escalations" && <JobsTab project={project} mode="escalations" />}
          </>
        );
      }}
    </Loaded>
  );
}

export default function ProjectPage() {
  return (
    <Suspense fallback={null}>
      <Workspace />
    </Suspense>
  );
}
