import { describe, expect, it } from "vitest";

import { localizeRecommendation } from "./recommendationLocale";

describe("deterministic recommendation localization", () => {
  it("translates the current high CO₂ and humidity message naturally", () => {
    expect(localizeRecommendation(
      "CO2 and humidity are high. Increase fresh-air ventilation and reduce excess humidity.",
    )).toBe(
      "ค่า CO₂ และความชื้นอยู่ในระดับสูง ควรเพิ่มการถ่ายเทอากาศจากภายนอก และลดความชื้นส่วนเกิน",
    );
  });

  it("handles the backend's good, single-factor, and mixed-factor wording", () => {
    expect(localizeRecommendation(
      "Room conditions are within the configured comfort range. Continue monitoring.",
    )).toContain("ติดตามสภาพแวดล้อมต่อเนื่อง");
    expect(localizeRecommendation(
      "CO2 is elevated. Improve ventilation and continue monitoring the room.",
    )).toContain("ค่า CO₂ ค่อนข้างสูง");
    expect(localizeRecommendation(
      "CO2 is high and humidity is elevated. Increase fresh-air ventilation and improve airflow.",
    )).toBe("ค่า CO₂ อยู่ในระดับสูง และความชื้นค่อนข้างสูง ควรเพิ่มการถ่ายเทอากาศจากภายนอก และเพิ่มการไหลเวียนของอากาศ");
    expect(localizeRecommendation(
      "CO2, room temperature, and humidity are high. Increase fresh-air ventilation, improve cooling or air circulation, and reduce excess humidity.",
    )).toContain("ค่า CO₂ อุณหภูมิ และความชื้นอยู่ในระดับสูง");
    expect(localizeRecommendation(
      "CO2 is high and room temperature is above the configured comfort range. Increase fresh-air ventilation and consider improving air circulation or cooling.",
    )).toContain("อุณหภูมิค่อนข้างสูง");
    expect(localizeRecommendation(
      "Room temperature and humidity are high. Improve cooling or air circulation and reduce excess humidity.",
    )).toContain("อุณหภูมิ และความชื้นอยู่ในระดับสูง");
    expect(localizeRecommendation(
      "Room temperature is above the configured comfort range and humidity is high. Consider improving air circulation or cooling and reduce excess humidity.",
    )).toContain("อุณหภูมิค่อนข้างสูง และความชื้นอยู่ในระดับสูง");
  });

  it("leaves unrecognized backend text unchanged rather than guessing", () => {
    expect(localizeRecommendation("A custom recommendation"))
      .toBe("A custom recommendation");
  });
});
