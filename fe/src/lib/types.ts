export type UserSummary = { id: string; email: string; full_name: string; status: string };

export type RoleAssignment = {
  id: string;
  role: string;
  granted_at: string;
  expires_at: string | null;
};

export type User = {
  id: string;
  kind: string;
  email: string;
  full_name: string;
  employee_code: string | null;
  status: string;
  employment_type: string;
  joined_at: string | null;
  left_at: string | null;
  activated: boolean;
  platform_roles: RoleAssignment[];
};

export type Page<T> = { items: T[]; total: number; limit: number; offset: number };

export type MyTeam = {
  team_id: string;
  code: string;
  name: string;
  team_role: string;
  is_lead: boolean;
};

export type Project = {
  id: string;
  code: string;
  name: string;
  description: string | null;
  status: string;
  data_classification: string;
  owner_id: string;
  created_at: string;
  my_roles: string[];
  my_permissions: string[];
};

export type Member = {
  id: string;
  user: UserSummary;
  role: string;
  assigned_at: string;
  expires_at: string | null;
};

export type TeamSummary = {
  id: string;
  code: string;
  name: string;
  description: string | null;
  status: string;
  annotators: number;
  reviewers: number;
  lead: UserSummary | null;
};

export type TeamMember = {
  id: string;
  user: UserSummary;
  team_role: string;
  is_lead: boolean;
  added_at: string;
  expires_at: string | null;
};

export type TeamDetail = TeamSummary & { members: TeamMember[] };

export type ProjectTeam = {
  id: string;
  team_id: string;
  code: string;
  name: string;
  annotators: number;
  reviewers: number;
  assigned_at: string;
};

export type Guideline = { id: string; version: number; created_at: string; content?: string };

export type ReasonCode = {
  id: string;
  code: string;
  label: string;
  default_severity: string;
  applies_to: string;
  active: boolean;
};

export type Dataset = {
  id: string;
  version: number;
  item_count: number;
  item_type: string;
  checksum: string;
  parser: string;
  parser_options: Record<string, string>;
  parser_version: string;
  parse_report: ParseReport;
  created_at: string;
};

export type ParseReport = {
  lines_total: number;
  lines_ok: number;
  error_count: number;
  errors: { line: number; code: string; message: string }[];
};

export type Step =
  | { id: string; type: "user" | "thought" | "assistant" | "tool_result"; content: string }
  | { id: string; type: "tool_call"; tool: string; args: Record<string, unknown> };

export type ItemPayload = {
  user_message: string;
  tools: { name: string; description?: string; params?: unknown }[];
  steps: Step[];
  targets: string[];
};

export type JobItem = { id: string; ordinal: number; external_ref: string | null; payload: ItemPayload };

export type FieldDef = {
  name: string;
  label?: string;
  type: "enum" | "multi_select" | "text" | "number" | "boolean";
  required?: boolean;
  options?: string[];
  options_from?: string;
  max_length?: number;
  visible_if?: { field: string; equals: unknown };
};

export type LabelSchema = {
  fields: FieldDef[];
  unsure_field?: { field: string; equals: unknown };
};

export type JobConfig = {
  id: string;
  version: number;
  item_type: string;
  label_schema: LabelSchema;
  job_rules: Record<string, number | string>;
  self_check: string[];
  created_at: string;
};

export type Task = {
  id: string;
  name: string;
  status: string;
  priority: number;
  team_id: string | null;
  dataset_version_id: string;
  job_config_id: string;
  guideline_version_id: string;
  created_at: string;
  delivered_at: string | null;
  jobs_total: number;
  by_status: Record<string, number>;
};

export type Job = {
  id: string;
  project_id: string;
  task_id: string;
  ordinal: number;
  status: string;
  assignee_id: string | null;
  reviewer_id: string | null;
  rework_count: number;
  has_unsure: boolean;
  lease_expires_at: string | null;
  assigned_at: string | null;
  submitted_at: string | null;
  closed_at: string | null;
};

export type ReviewErrorView = {
  item_id: string;
  target: string | null;
  reason_code: string;
  severity: string;
  note: string | null;
};

export type LabelValue = Record<string, unknown>;

export type RoundView = {
  round: number;
  submitted_at: string;
  annotations: { item_id: string; target: string | null; value: LabelValue; is_unsure: boolean }[];
  review: { decision: string; reason: string | null; errors: ReviewErrorView[] } | null;
};

export type JobView = {
  job: Job;
  task: { id: string; name: string };
  guideline: { version: number; content: string };
  config: {
    version: number;
    item_type: string;
    label_schema: LabelSchema;
    self_check: string[];
    max_rework: number;
  };
  rework_remaining: number;
  reason_codes: { code: string; label: string; default_severity: string; applies_to: string }[];
  items: JobItem[];
  draft: Record<string, LabelValue> | null;
  last_review: {
    decision: string;
    reason: string | null;
    created_at: string;
    errors: ReviewErrorView[];
  } | null;
  rounds?: RoundView[];
  my_role?: string;
};

export type Queue = {
  project: { id: string; code: string; name: string; status: string };
  roles: string[];
  active: boolean;
  my_jobs: Job[];
  my_reviews: Job[];
  waiting_for_review: number;
};

export type Progress = {
  jobs_total: number;
  by_status: Record<string, number>;
  completion_rate: number;
  backlog: number;
  throughput_per_day: number;
  cycle_time_hours: { p50: number | null; p90: number | null };
  first_pass_rate: number | null;
  stuck: number;
  as_of: string;
};

export type Acceptance = Progress & {
  task_status: string;
  open_jobs: number;
  can_sign_off: boolean;
  sample_job_ids: string[];
};

export type AuditEvent = {
  id: string;
  actor_name: string;
  action: string;
  target_type: string;
  target_id: string | null;
  reason: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  ip: string | null;
  created_at: string;
};

export type Workload = {
  user_id: string;
  user: UserSummary;
  annotate: number;
  review: number;
  roles: string[];
};
