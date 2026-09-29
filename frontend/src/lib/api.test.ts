import { afterEach, describe, expect, it, vi } from "vitest";

import { getAiAssessment } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AI assessment API client", () => {
  it("posts only the device ID and selected sensitivities to the existing endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, source: "fallback" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await getAiAssessment({
      device_id: "smart-room-01",
      sensitivities: ["poor_ventilation_sensitive", "high_humidity_sensitive"],
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(/\/api\/v1\/ai\/assessment$/);
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ "Content-Type": "application/json" });
    expect(JSON.parse(init.body as string)).toEqual({
      device_id: "smart-room-01",
      sensitivities: ["poor_ventilation_sensitive", "high_humidity_sensitive"],
    });
    expect(Object.keys(JSON.parse(init.body as string))).toEqual(["device_id", "sensitivities"]);
  });
});
