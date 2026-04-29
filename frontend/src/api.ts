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
