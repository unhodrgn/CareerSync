import type {
  ApplicantList,
  ApplicationOut,
  ApplicationStatus,
  CheckResult,
  Company,
  CriteriaSetOut,
  CriterionIn,
  CvOut,
  CvProfile,
  EvaluationOut,
  Job,
  JobInput,
  JobListItem,
  JobPage,
  RegisterBody,
  SeekerCriteriaSetOut,
  User,
} from "./types";

const TOKEN_KEY = "careersync.token";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public extra: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

export const tokenStore = {
  get(): string | null {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(token: string | null) {
    try {
      if (token) localStorage.setItem(TOKEN_KEY, token);
      else localStorage.removeItem(TOKEN_KEY);
    } catch {
      // storage unavailable: the session just won't survive a reload
    }
  },
};

let onUnauthorized: () => void = () => {};
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;
  const isForm = body instanceof FormData;
  // FormData sets its own multipart boundary header
  if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";

  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "NETWORK", "서버에 연결할 수 없습니다. 백엔드가 실행 중인지 확인하세요.");
  }

  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (res.ok) return data as T;

  // AppError renders {code, message, ...}; FastAPI validation errors render {detail: [...]}
  if (data && typeof data.code === "string") {
    const { code, message, ...extra } = data;
    if (res.status === 401 && token && path !== "/auth/login") onUnauthorized();
    throw new ApiError(res.status, code, message, extra);
  }
  if (data && Array.isArray(data.detail)) {
    const text = data.detail.map((d: { msg?: string }) => (d.msg ?? "").replace(/^Value error, /, "")).join(" ");
    throw new ApiError(res.status, "VALIDATION", text || "입력값이 올바르지 않습니다.");
  }
  throw new ApiError(res.status, "UNKNOWN", `요청에 실패했습니다. (${res.status})`);
}

export const api = {
  register: (body: RegisterBody) => request<User>("POST", "/auth/register", body),
  login: (email: string, password: string) =>
    request<{ access_token: string; expires_in: number }>("POST", "/auth/login", { email, password }),
  me: () => request<User>("GET", "/users/me"),

  myCompany: () => request<Company>("GET", "/companies/me"),
  updateCompany: (body: Pick<Company, "name" | "intro" | "talent_profile">) =>
    request<Company>("PUT", "/companies/me", body),

  publicJobs: (q: string) => request<JobPage>("GET", `/jobs?limit=50${q ? `&q=${encodeURIComponent(q)}` : ""}`),
  myJobs: () => request<JobListItem[]>("GET", "/jobs/mine"),
  job: (id: number) => request<Job>("GET", `/jobs/${id}`),
  createJob: (body: JobInput) => request<Job>("POST", "/jobs", body),
  updateJob: (id: number, body: Partial<JobInput>) => request<Job>("PATCH", `/jobs/${id}`, body),
  deleteJob: (id: number) => request<void>("DELETE", `/jobs/${id}`),
  publishJob: (id: number) => request<Job>("POST", `/jobs/${id}/publish`),
  closeJob: (id: number) => request<Job>("POST", `/jobs/${id}/close`),

  criteria: (jobId: number) => request<CriteriaSetOut>("GET", `/jobs/${jobId}/criteria`),
  seekerCriteria: (jobId: number) => request<SeekerCriteriaSetOut>("GET", `/jobs/${jobId}/criteria`),
  saveCriteria: (jobId: number, items: CriterionIn[]) =>
    request<CriteriaSetOut>("PUT", `/jobs/${jobId}/criteria`, { items }),
  copyCriteria: (jobId: number, sourceId: number) =>
    request<CriteriaSetOut>("POST", `/jobs/${jobId}/criteria/copy-from/${sourceId}`),
  checkCriterion: (name: string, description: string) =>
    request<CheckResult>("POST", "/criteria/check", { name, description }),

  uploadCv: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<CvOut>("POST", "/cv", form);
  },
  myCv: () => request<CvOut>("GET", "/cv/me"),
  updateCv: (profileId: number, profile: CvProfile, confirm = true) =>
    request<CvOut>("PUT", `/cv/${profileId}`, { profile, confirm }),

  apply: (jobId: number) => request<ApplicationOut>("POST", `/jobs/${jobId}/applications`),
  myApplications: () => request<ApplicationOut[]>("GET", "/applications/mine"),
  applicants: (jobId: number) => request<ApplicantList>("GET", `/jobs/${jobId}/applications`),
  evaluation: (applicationId: number) => request<EvaluationOut>("GET", `/applications/${applicationId}/evaluation`),
  retryEvaluation: (applicationId: number) =>
    request<EvaluationOut>("POST", `/applications/${applicationId}/evaluation/retry`),
  setApplicationStatus: (applicationId: number, status: ApplicationStatus) =>
    request<ApplicationOut>("PUT", `/applications/${applicationId}/status`, { status }),
};
