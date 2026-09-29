import { StrictMode } from "react";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { getAiAssessment, getLatestReading, getReadingHistory } from "./lib/api";
import { PROFILE_STORAGE_KEY } from "./lib/profile";
import type { AiAssessmentResponse } from "./types/ai";
import type { HistoryReading, LatestReadingResponse } from "./types/readings";

vi.mock("./lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./lib/api")>();
  return {
    ...actual,
    getLatestReading: vi.fn(),
    getReadingHistory: vi.fn(),
    getAiAssessment: vi.fn(),
  };
});

const latest: LatestReadingResponse = {
  success: true,
  status: "HOT",
  recommendation: "CO2 and humidity are high. Increase fresh-air ventilation and reduce excess humidity.",
  data: {
    device_id: "smart-room-01",
    temperature: 26.34,
    humidity: 87.34,
    co2: 2093,
    fan_on: true,
  },
};

const history: HistoryReading[] = [{
  ...latest.data,
  id: 1,
  status: "HOT",
  recommendation: latest.recommendation,
  created_at: "2026-09-29T08:00:00Z",
}];

const fallbackResponse: AiAssessmentResponse = {
  success: true,
  source: "fallback",
  device_id: "smart-room-01",
  profile: ["poor_ventilation_sensitive", "high_humidity_sensitive"],
  environment: { temperature: 26.34, humidity: 87.34, co2: 2093, status: "HOT" },
  assessment: {
    suitability: "NOT_SUITABLE",
    title: "สภาพแวดล้อมตอนนี้อาจไม่เหมาะกับคุณ",
    summary: "ค่า CO₂ ประมาณ 2,093 ppm และความชื้น 87.3% ค่อนข้างสูง",
    reasons: ["ค่า CO₂ ค่อนข้างสูง", "ความชื้นค่อนข้างสูง"],
    recommendations: ["ลองเพิ่มการระบายอากาศ", "ใช้เครื่องลดความชื้นหากมี"],
  },
  disclaimer: "คำแนะนำนี้อ้างอิงจากค่า CO₂ อุณหภูมิ ความชื้น และลักษณะที่คุณเลือก ไม่ใช่การวินิจฉัยทางการแพทย์",
};

beforeEach(() => {
  window.sessionStorage.clear();
  vi.clearAllMocks();
  vi.mocked(getLatestReading).mockResolvedValue(latest);
  vi.mocked(getReadingHistory).mockResolvedValue(history);
  vi.mocked(getAiAssessment).mockResolvedValue(fallbackResponse);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

async function selectAndConfirm(label = "ไวต่ออากาศอับหรือการระบายอากาศไม่ดี") {
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: label }));
  await user.click(screen.getByRole("button", { name: "ยืนยันและเริ่มวิเคราะห์" }));
  return user;
}

describe("AI environmental dashboard", () => {
  it("requires one of the six supported sensitivities in a new session", async () => {
    render(<App />);
    expect(screen.getByRole("dialog", { name: "ผู้ช่วย AI วิเคราะห์สภาพแวดล้อมเพื่อสุขภาพ" })).toBeTruthy();
    expect(screen.getByText("กรุณาเลือกลักษณะที่ตรงกับสุขภาพของคุณอย่างน้อย 1 ข้อ")).toBeTruthy();
    expect(screen.getAllByRole("button", { pressed: false })).toHaveLength(6);
    expect(screen.getByRole("button", { name: "ยืนยันและเริ่มวิเคราะห์" }).hasAttribute("disabled")).toBe(true);
    expect(vi.mocked(getAiAssessment)).not.toHaveBeenCalled();
    expect(screen.queryByText(/PM2\.5|แพ้ฝุ่น|ละอองเกสร/)).toBeNull();
  });

  it("sends only device_id and selected IDs, then renders a fallback assessment normally", async () => {
    render(<App />);
    await selectAndConfirm();
    await waitFor(() => expect(getAiAssessment).toHaveBeenCalledTimes(1));
    const request = vi.mocked(getAiAssessment).mock.calls[0][0];
    expect(request).toEqual({
      device_id: "smart-room-01",
      sensitivities: ["poor_ventilation_sensitive"],
    });
    expect(Object.keys(request)).toEqual(["device_id", "sensitivities"]);
    expect(window.sessionStorage.getItem(PROFILE_STORAGE_KEY)).toBe('["poor_ventilation_sensitive"]');
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(await screen.findByText(fallbackResponse.assessment.summary)).toBeTruthy();
    expect(screen.getByText("อาจไม่เหมาะกับคุณ")).toBeTruthy();
    expect(screen.getByText("เหตุผลที่ควรสังเกต")).toBeTruthy();
    expect(screen.getByText("คำแนะนำสำหรับคุณ")).toBeTruthy();
    expect(screen.getByText(fallbackResponse.disclaimer)).toBeTruthy();
    expect(screen.getByText("การประเมินสภาพแวดล้อม")).toBeTruthy();
    expect(screen.getByText("ค่า CO₂ และความชื้นอยู่ในระดับสูง ควรเพิ่มการถ่ายเทอากาศจากภายนอก และลดความชื้นส่วนเกิน")).toBeTruthy();
    expect(screen.getByText("ประวัติข้อมูลสภาพแวดล้อม")).toBeTruthy();
    expect(screen.getByText("26.3")).toBeTruthy();
  });

  it("restores the session profile and requests one assessment after reload", async () => {
    window.sessionStorage.setItem(PROFILE_STORAGE_KEY, '["high_humidity_sensitive"]');
    render(<StrictMode><App /></StrictMode>);
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(getAiAssessment).toHaveBeenCalledTimes(1));
    expect(vi.mocked(getAiAssessment).mock.calls[0][0].sensitivities).toEqual(["high_humidity_sensitive"]);
  });

  it("preselects saved options and reassesses when the profile changes", async () => {
    render(<App />);
    const user = await selectAndConfirm();
    await waitFor(() => expect(getAiAssessment).toHaveBeenCalledTimes(1));
    await user.click(screen.getByRole("button", { name: "แก้ไขข้อมูลสุขภาพ" }));
    expect(screen.getByRole("button", { name: "ไวต่ออากาศอับหรือการระบายอากาศไม่ดี" }).getAttribute("aria-pressed")).toBe("true");
    await user.click(screen.getByRole("button", { name: "ไวต่อความชื้นสูง" }));
    await user.click(screen.getByRole("button", { name: "ยืนยันและเริ่มวิเคราะห์" }));
    await waitFor(() => expect(getAiAssessment).toHaveBeenCalledTimes(2));
    expect(vi.mocked(getAiAssessment).mock.calls[1][0].sensitivities).toEqual([
      "poor_ventilation_sensitive", "high_humidity_sensitive",
    ]);
    expect(JSON.parse(window.sessionStorage.getItem(PROFILE_STORAGE_KEY) ?? "null")).toEqual([
      "poor_ventilation_sensitive", "high_humidity_sensitive",
    ]);
  });

  it("reanalyzes manually without coupling AI calls to the five-second telemetry poll", async () => {
    const intervalSpy = vi.spyOn(window, "setInterval");
    render(<App />);
    const user = await selectAndConfirm();
    await waitFor(() => expect(getAiAssessment).toHaveBeenCalledTimes(1));
    await user.click(screen.getByRole("button", { name: "วิเคราะห์อีกครั้ง" }));
    await waitFor(() => expect(getAiAssessment).toHaveBeenCalledTimes(2));
    const poll = intervalSpy.mock.calls.find(([, delay]) => delay === 5_000)?.[0];
    expect(typeof poll).toBe("function");
    if (typeof poll === "function") {
      await act(async () => { poll(); });
    }
    expect(getLatestReading).toHaveBeenCalledTimes(2);
    expect(getReadingHistory).toHaveBeenCalledTimes(2);
    expect(getAiAssessment).toHaveBeenCalledTimes(2);
    intervalSpy.mockRestore();
  });

  it("keeps telemetry available and polling while AI is still loading", async () => {
    const intervalSpy = vi.spyOn(window, "setInterval");
    vi.mocked(getAiAssessment).mockImplementation(() => new Promise(() => {}));
    render(<App />);
    await selectAndConfirm();
    await waitFor(() => expect(getAiAssessment).toHaveBeenCalledTimes(1));
    expect(screen.getByText("AI กำลังวิเคราะห์สภาพแวดล้อมสำหรับคุณ...")).toBeTruthy();
    expect(screen.getByText("ค่าปัจจุบัน")).toBeTruthy();
    const poll = intervalSpy.mock.calls.find(([, delay]) => delay === 5_000)?.[0];
    if (typeof poll === "function") {
      await act(async () => { poll(); });
    }
    expect(getLatestReading).toHaveBeenCalledTimes(2);
    expect(getAiAssessment).toHaveBeenCalledTimes(1);
    intervalSpy.mockRestore();
  });

  it("shows a retry state on AI failure while telemetry remains visible", async () => {
    vi.mocked(getAiAssessment).mockRejectedValueOnce(new Error("provider unavailable"));
    render(<App />);
    const user = await selectAndConfirm();
    expect(await screen.findByText("ยังไม่สามารถวิเคราะห์ข้อมูลสำหรับคุณได้ในขณะนี้ กรุณาลองใหม่อีกครั้ง")).toBeTruthy();
    expect(screen.getByText("ค่าปัจจุบัน")).toBeTruthy();
    expect(screen.getByText("ประวัติข้อมูลสภาพแวดล้อม")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "ลองวิเคราะห์อีกครั้ง" }));
    await waitFor(() => expect(getAiAssessment).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(fallbackResponse.assessment.summary)).toBeTruthy();
  });
});
