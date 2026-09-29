import type { HistoryReading, LatestReadingResponse } from "../types/readings";
import type { AiAssessmentRequest, AiAssessmentResponse } from "../types/ai";

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"
).replace(/\/$/, "");

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, init);
  } catch (error) {
    if (init?.signal?.aborted) {
      throw error;
    }
    throw new ApiError(
      0,
      "Unable to reach the backend. Check that FastAPI is running.",
    );
  }

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}.`;

    try {
      const body: unknown = await response.json();
      if (
        typeof body === "object" &&
        body !== null &&
        "detail" in body &&
        typeof body.detail === "string"
      ) {
        detail = body.detail;
      }
    } catch {
      // Keep the status-based message when the backend has no JSON error body.
    }

    throw new ApiError(response.status, detail);
  }

  return response.json() as Promise<T>;
}

export function getLatestReading(): Promise<LatestReadingResponse> {
  return requestJson<LatestReadingResponse>("/api/v1/readings/latest");
}

export function getReadingHistory(limit = 50): Promise<HistoryReading[]> {
  return requestJson<HistoryReading[]>(`/api/v1/readings?limit=${limit}`);
}

export function getAiAssessment(
  request: AiAssessmentRequest,
  signal?: AbortSignal,
): Promise<AiAssessmentResponse> {
  return requestJson<AiAssessmentResponse>("/api/v1/ai/assessment", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal,
  });
}
