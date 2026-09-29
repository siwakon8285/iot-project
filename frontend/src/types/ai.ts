import type { RoomStatus } from "./readings";

export const SENSITIVITY_OPTIONS = [
  { id: "heat_sensitive", label: "ร้อนง่าย / ไวต่ออากาศร้อน" },
  { id: "cold_sensitive", label: "ขี้หนาว / ไวต่ออากาศเย็น" },
  { id: "high_humidity_sensitive", label: "ไวต่อความชื้นสูง" },
  { id: "dry_air_sensitive", label: "ไวต่ออากาศแห้ง" },
  { id: "poor_ventilation_sensitive", label: "ไวต่ออากาศอับหรือการระบายอากาศไม่ดี" },
  { id: "respiratory_sensitive", label: "ระบบทางเดินหายใจไวต่อสภาพแวดล้อม" },
] as const;

export type Sensitivity = (typeof SENSITIVITY_OPTIONS)[number]["id"];
export type AiSuitability = "SUITABLE" | "CAUTION" | "NOT_SUITABLE";

export interface AiAssessmentRequest {
  device_id: string;
  sensitivities: Sensitivity[];
}

export interface AiAssessmentResponse {
  success: boolean;
  source: "groq" | "fallback";
  device_id: string;
  profile: Sensitivity[];
  environment: {
    temperature: number;
    humidity: number;
    co2: number | null;
    status: RoomStatus;
  };
  assessment: {
    suitability: AiSuitability;
    title: string;
    summary: string;
    reasons: string[];
    recommendations: string[];
  };
  disclaimer: string;
}

const sensitivityIds: ReadonlySet<string> = new Set(SENSITIVITY_OPTIONS.map((option) => option.id));

export function isSensitivity(value: unknown): value is Sensitivity {
  return typeof value === "string" && sensitivityIds.has(value);
}
