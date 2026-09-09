const configuredApiBaseUrl = (import.meta.env["VITE_API_BASE_URL"] as string | undefined)?.trim();

export const API_BASE_URL = configuredApiBaseUrl
  ? configuredApiBaseUrl.replace(/\/$/, "")
  : import.meta.env.PROD
    ? ""
    : "http://127.0.0.1:8000";

const ACCESS_TOKEN_KEY = "nextcare.staff_access_token";
export const AUTH_EXPIRED_EVENT = "nextcare:authentication-expired";

export type ApiErrorEnvelope = {
  error: { code: string; detail: string; issues?: Array<Record<string, unknown>> };
};

export type StaffUser = {
  id: string;
  email: string;
  full_name: string;
  role: "DOCTOR" | "NURSE" | "ADMIN";
  is_active: boolean;
  created_at: string;
};

export type StaffTokenResponse = {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  staff: StaffUser;
};

export class NeurobotsApiError extends Error {
  code: string;
  status: number;

  constructor(status: number, code: string, detail: string) {
    super(detail);
    this.name = "NeurobotsApiError";
    this.status = status;
    this.code = code;
  }
}

export type Patient = {
  id: string;
  external_patient_id: string;
  first_name: string;
  last_name: string;
  date_of_birth: string;
  gender: string;
  phone_number: string | null;
  created_at: string;
  updated_at: string;
};

export type Symptom = {
  id: string;
  encounter_id: string;
  name: string;
  severity: number | null;
  duration: string | null;
  onset: string | null;
  present: boolean;
  source: string;
  created_at: string;
};

export type VitalSigns = {
  id: string;
  encounter_id: string;
  heart_rate: number | null;
  systolic_bp: number | null;
  diastolic_bp: number | null;
  spo2: number | null;
  respiratory_rate: number | null;
  temperature: number | null;
  measured_at: string;
  source: string;
};

export type LabResult = {
  id: string;
  encounter_id: string;
  test_name: string;
  value: number;
  unit: string | null;
  collected_at: string;
  source: string;
  reference_metadata: Record<string, unknown> | null;
};

export type Encounter = {
  id: string;
  patient_id: string;
  encounter_type: string;
  chief_complaint: string;
  clinician_notes: string | null;
  status: string;
  started_at: string;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  symptoms: Symptom[];
  vital_signs: VitalSigns[];
  lab_results: LabResult[];
};

export type QueueEntry = {
  id: string;
  encounter_id: string;
  patient_id: string;
  patient_display: {
    display_name: string;
    age_years: number;
    chief_complaint: string;
  };
  queue_status: string;
  priority_score: number;
  priority_band: string;
  rank: number | null;
  waiting_since: string;
  waiting_duration_minutes: number;
  prototype_esi_level: number | null;
  triage_severity: string;
  cardiac_risk_probability: number | null;
  cardiac_risk_model_version: string | null;
  deterioration_status: string;
  provisional: boolean;
  reason_codes: string[];
  policy_name: string;
  policy_version: string;
  triage_assessment_id: string;
  risk_prediction_id: string | null;
  last_reassessment_at: string;
  created_at: string;
  updated_at: string;
};

export type PendingQueueEntry = {
  id: string;
  patient_id: string;
  encounter_id: string | null;
  patient_display: QueueEntry["patient_display"];
  intake_stage: "REGISTRATION" | "TRIAGE";
  waiting_since: string;
  waiting_duration_minutes: number;
};

export type Assessment = {
  patient: Patient;
  encounter: Encounter;
  cardiac_risk: Record<string, unknown> | null;
  triage: Record<string, unknown> | null;
  explanation: Record<string, unknown> | null;
  clinical_reasoning: Record<string, unknown> | null;
  priority: Record<string, unknown> | null;
  documents: Array<Record<string, unknown>>;
  speech: Array<Record<string, unknown>>;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const accessToken = getAccessToken();
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        ...(init?.headers ?? {}),
      },
    });
  } catch (error) {
    throw new NeurobotsApiError(
      0,
      "BACKEND_UNAVAILABLE",
      error instanceof Error ? error.message : "Backend unavailable",
    );
  }
  if (!response.ok) {
    let code = `HTTP_${response.status}`;
    let detail = `Request failed with status ${response.status}`;
    try {
      const payload = (await response.json()) as Partial<ApiErrorEnvelope>;
      code = payload.error?.code ?? code;
      detail = payload.error?.detail ?? detail;
      const validationDetails = payload.error?.issues
        ?.map(validationIssueMessage)
        .filter((message): message is string => Boolean(message));
      if (validationDetails?.length) detail = `${detail}: ${validationDetails.join("; ")}`;
    } catch {
      // Preserve the stable HTTP fallback when the backend did not return JSON.
    }
    if (response.status === 401 && path !== "/api/auth/login") {
      clearAccessToken();
      if (typeof window !== "undefined") window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
    }
    throw new NeurobotsApiError(response.status, code, detail);
  }
  return (await response.json()) as T;
}

function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(ACCESS_TOKEN_KEY);
}

function storeAccessToken(token: string): void {
  if (typeof window !== "undefined") window.sessionStorage.setItem(ACCESS_TOKEN_KEY, token);
}

function clearAccessToken(): void {
  if (typeof window !== "undefined") window.sessionStorage.removeItem(ACCESS_TOKEN_KEY);
}

function validationIssueMessage(issue: Record<string, unknown>): string | null {
  if (typeof issue["message"] !== "string") return null;
  const location = Array.isArray(issue["location"])
    ? issue["location"].filter((part) => part !== "body").at(-1)
    : null;
  return location ? `${String(location)}: ${issue["message"]}` : issue["message"];
}

function json(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export const api = {
  health: () => request<{ status: string; service: string; environment: string }>("/health"),
  hasStaffSession: () => Boolean(getAccessToken()),
  login: async (email: string, password: string) => {
    const response = await request<StaffTokenResponse>(
      "/api/auth/login",
      json("POST", { email, password }),
    );
    storeAccessToken(response.access_token);
    return response;
  },
  currentStaff: () => request<StaffUser>("/api/auth/me"),
  logout: () => clearAccessToken(),
  listQueue: () => request<QueueEntry[]>("/api/queue"),
  listPendingQueue: () => request<PendingQueueEntry[]>("/api/queue/pending"),
  updateQueueStatus: (queueId: string, queue_status: string) =>
    request<QueueEntry>(`/api/queue/${queueId}`, json("PATCH", { queue_status })),
  getAssessment: (encounterId: string) =>
    request<Assessment>(`/api/encounters/${encounterId}/assessment`),
  runWorkflow: (encounterId: string) =>
    request<Record<string, unknown>>(`/api/encounters/${encounterId}/workflow`, { method: "POST" }),
  searchPatients: (query: string) => {
    const params = new URLSearchParams({ limit: "25" });
    if (query.trim()) params.set("name", query.trim());
    return request<Patient[]>(`/api/patients?${params.toString()}`);
  },
  createPatient: (payload: Record<string, unknown>) =>
    request<Patient>("/api/patients", json("POST", payload)),
  patientHistory: (patientId: string) =>
    request<{ patient: Patient; encounters: Encounter[] }>(`/api/patients/${patientId}/history`),
  createEncounter: (patientId: string, payload: Record<string, unknown>) =>
    request<Encounter>(`/api/patients/${patientId}/encounters`, json("POST", payload)),
  addSymptom: (encounterId: string, payload: Record<string, unknown>) =>
    request<Symptom>(`/api/encounters/${encounterId}/symptoms`, json("POST", payload)),
  addVitals: (encounterId: string, payload: Record<string, unknown>) =>
    request<VitalSigns>(`/api/encounters/${encounterId}/vitals`, json("POST", payload)),
  addLab: (encounterId: string, payload: Record<string, unknown>) =>
    request<LabResult>(`/api/encounters/${encounterId}/labs`, json("POST", payload)),
  uploadDocument: (encounterId: string, file: File) =>
    request<Record<string, unknown>>(`/api/encounters/${encounterId}/documents`, {
      method: "POST",
      headers: { "Content-Type": file.type, "X-Filename": file.name },
      body: file,
    }),
  uploadSpeech: (encounterId: string, file: File) =>
    request<Record<string, unknown>>(`/api/encounters/${encounterId}/speech`, {
      method: "POST",
      headers: { "Content-Type": audioContentType(file), "X-Filename": file.name },
      body: file,
    }),
};

function audioContentType(file: File): string {
  const declaredType = file.type.split(";", 1)[0]?.toLowerCase() ?? "";
  const aliases: Record<string, string> = {
    "audio/m4a": "audio/mp4",
    "audio/vnd.wave": "audio/wav",
    "audio/wave": "audio/wav",
    "application/ogg": "audio/ogg",
  };
  if (declaredType && declaredType !== "application/octet-stream") {
    return aliases[declaredType] || declaredType;
  }
  const extension = file.name.split(".").pop()?.toLowerCase();
  const byExtension: Record<string, string> = {
    flac: "audio/flac",
    m4a: "audio/mp4",
    mp3: "audio/mpeg",
    mp4: "audio/mp4",
    mpeg: "audio/mpeg",
    mpga: "audio/mpeg",
    ogg: "audio/ogg",
    wav: "audio/wav",
    webm: "audio/webm",
  };
  return (extension && byExtension[extension]) || "application/octet-stream";
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong";
}
