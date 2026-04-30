export type HealthResponse = {
  status: string;
};

export type AdapterResponse = {
  metadata: {
    name: string;
    display_name: string;
    tier: string;
    access_mode: string;
  };
  status: string;
  disabled_reason: string | null;
};

export type SearchResponse = {
  id: string | null;
  parsed_jd: {
    title: string;
    required_skills: string[];
    location: string | null;
    pay_rate: number | null;
    shift: string | null;
  };
  candidates: Array<{
    score: number;
    reasoning: string;
    candidate: {
      name: string;
      source: string;
      current_title: string | null;
      location: string | null;
      skills: string[];
    };
  }>;
  adapter_stats: Array<{
    source: string;
    candidates_found: number;
    duration_ms: number;
    error: string | null;
  }>;
};

export type SourcePlanResponse = {
  parsed_jd: SearchResponse["parsed_jd"] & {
    title_variants: string[];
    required_certs: string[];
  };
  state: string | null;
  city: string | null;
  message: string | null;
  recommended_portals: Array<{
    portal: {
      id: string;
      state: string;
      state_name: string;
      name: string;
      employer_url: string;
      automation_mode: string;
      credential_env_vars: string[];
      search_notes: string;
      usage_guidance: string;
    };
    search_terms: string[];
    suggested_filters: string[];
    automation_ready: boolean;
    readiness_messages: string[];
    capture_guidance: string;
  }>;
};

export type PortalRunResponse = {
  id: string | null;
  status: "not_ready" | "running" | "completed" | "failed";
  portal: SourcePlanResponse["recommended_portals"][number]["portal"];
  parsed_jd: SourcePlanResponse["parsed_jd"];
  search_terms: string[];
  candidates: Array<{
    candidate_id: string | null;
    saved: boolean;
    skipped_reason: string | null;
    candidate: {
      source: string;
      source_id: string;
      profile_url: string | null;
      name: string;
      current_title: string | null;
      location: string | null;
      skills: string[];
      contact: {
        email: string | null;
        phone: string | null;
      };
    };
  }>;
  candidates_found: number;
  candidates_saved: number;
  candidates_skipped: number;
  warnings: string[];
  error: string | null;
};

export type CandidateSummary = PortalRunResponse["candidates"][number]["candidate"];

const rawBaseUrl = import.meta.env.VITE_API_BASE_URL || "https://sourcing-backend-s6dr.onrender.com";
export const apiBaseUrl = rawBaseUrl.replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
    ...init,
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function getHealth() {
  return request<HealthResponse>("/health");
}

export function getAdapters() {
  return request<AdapterResponse[]>("/api/adapters");
}

export function runSearch(jdText: string) {
  return request<SearchResponse>("/api/search", {
    method: "POST",
    body: JSON.stringify({
      jd_text: jdText,
      mode: "external",
      include_premium: false,
      limit_per_source: 10,
    }),
  });
}

export function createSourcePlan(jdText: string, state: string) {
  return request<SourcePlanResponse>("/api/source-plan", {
    method: "POST",
    body: JSON.stringify({
      jd_text: jdText,
      state,
    }),
  });
}

export function runPortalSearch(jdText: string, state: string, portalId: string) {
  return request<PortalRunResponse>("/api/portal-runs", {
    method: "POST",
    body: JSON.stringify({
      jd_text: jdText,
      state,
      portal_id: portalId,
      limit: 25,
    }),
  });
}

export function getCandidates() {
  return request<CandidateSummary[]>("/api/candidates");
}
