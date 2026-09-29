import { isSensitivity, type Sensitivity } from "../types/ai";

export const PROFILE_STORAGE_KEY = "ai_environment_profile";

export function readSessionProfile(): Sensitivity[] | null {
  try {
    const stored = window.sessionStorage.getItem(PROFILE_STORAGE_KEY);
    if (!stored) {
      return null;
    }
    const parsed: unknown = JSON.parse(stored);
    if (!Array.isArray(parsed) || !parsed.length || !parsed.every(isSensitivity)) {
      return null;
    }
    return [...new Set(parsed)];
  } catch {
    return null;
  }
}

export function writeSessionProfile(sensitivities: Sensitivity[]): void {
  try {
    window.sessionStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(sensitivities));
  } catch {
    // The profile remains usable in memory if browser storage is unavailable.
  }
}
