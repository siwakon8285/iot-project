/** Translate the backend's existing recommendation wording for display only. */
const singleRecommendations: Record<string, string> = {
  "Room conditions are within the configured comfort range. Continue monitoring.":
    "ค่าที่วัดได้ตอนนี้อยู่ในช่วงที่สบาย ควรติดตามสภาพแวดล้อมต่อเนื่อง",
  "CO2 is high. Increase fresh-air ventilation and check room airflow. Maintaining good ventilation is especially important in rooms used by older adults or people with respiratory sensitivity.":
    "ค่า CO₂ อยู่ในระดับสูง ควรเพิ่มการถ่ายเทอากาศจากภายนอกและตรวจสอบการไหลเวียนของอากาศ โดยเฉพาะในพื้นที่ที่มีผู้สูงอายุหรือผู้ที่ไวต่ออากาศอับ",
  "CO2 is elevated. Improve ventilation and continue monitoring the room.":
    "ค่า CO₂ ค่อนข้างสูง ควรเพิ่มการถ่ายเทอากาศและติดตามค่าต่อเนื่อง",
  "Room temperature is high. Improve cooling or air circulation and continue monitoring patient comfort.":
    "อุณหภูมิอยู่ในระดับสูง ควรเพิ่มการไหลเวียนของอากาศหรือปรับความเย็น และสังเกตความสบายของคุณ",
  "Room temperature is above the configured comfort range. Consider improving air circulation or cooling.":
    "อุณหภูมิค่อนข้างสูง ลองเพิ่มการไหลเวียนของอากาศหรือปรับความเย็นให้สบายขึ้น",
  "Humidity is high. Improve ventilation or dehumidification to maintain a more comfortable room environment.":
    "ความชื้นอยู่ในระดับสูง ควรเพิ่มการถ่ายเทอากาศหรือใช้เครื่องลดความชื้นเพื่อให้สภาพแวดล้อมสบายขึ้น",
  "Humidity is elevated. Improve airflow and continue monitoring the room.":
    "ความชื้นค่อนข้างสูง ควรเพิ่มการไหลเวียนของอากาศและติดตามค่าต่อเนื่อง",
};

const factorNames: Record<string, string> = {
  CO2: "ค่า CO₂",
  "room temperature": "อุณหภูมิ",
  humidity: "ความชื้น",
};

const actionNames: Record<string, string> = {
  "increase fresh-air ventilation": "เพิ่มการถ่ายเทอากาศจากภายนอก",
  "improve ventilation": "เพิ่มการถ่ายเทอากาศ",
  "improve cooling or air circulation": "เพิ่มการระบายความร้อนหรือการไหลเวียนของอากาศ",
  "consider improving air circulation or cooling": "เพิ่มการไหลเวียนของอากาศหรือปรับความเย็นตามความเหมาะสม",
  "reduce excess humidity": "ลดความชื้นส่วนเกิน",
  "improve airflow": "เพิ่มการไหลเวียนของอากาศ",
};

function splitEnglishList(value: string): string[] {
  return value.split(/, and | and |, /).map((part) => part.trim());
}

function joinThai(items: string[]): string {
  if (items.length < 2) return items[0] ?? "";
  return `${items.slice(0, -1).join(" ")} และ${items[items.length - 1]}`;
}

function translateIssue(issue: string): string | null {
  const normalizedIssue = issue.replace(/^Room temperature/, "room temperature");
  const allHigh = /^(.+) are high$/.exec(normalizedIssue);
  if (allHigh) {
    const labels = splitEnglishList(allHigh[1]).map((part) => factorNames[part]);
    return labels.length > 1 && labels.every(Boolean)
      ? `${joinThai(labels)}อยู่ในระดับสูง`
      : null;
  }

  const clauses = splitEnglishList(normalizedIssue).map((part) => {
    if (part === "room temperature is above the configured comfort range") {
      return "อุณหภูมิค่อนข้างสูง";
    }
    const match = /^(CO2|room temperature|humidity) is (high|elevated)$/.exec(part);
    if (!match) return null;
    const label = factorNames[match[1]];
    const predicate = match[2] === "high" ? "อยู่ในระดับสูง" : "ค่อนข้างสูง";
    return `${label}${label === "ค่า CO₂" ? " " : ""}${predicate}`;
  });
  return clauses.every(Boolean) ? joinThai(clauses as string[]) : null;
}

export function localizeRecommendation(recommendation: string): string {
  if (Object.prototype.hasOwnProperty.call(singleRecommendations, recommendation)) {
    return singleRecommendations[recommendation];
  }

  const match = /^(.+)\. (.+)\.$/.exec(recommendation);
  if (!match) return recommendation;

  const issue = translateIssue(match[1]);
  const actions = splitEnglishList(match[2].toLowerCase()).map((part) => actionNames[part]);
  if (!issue || actions.length === 0 || actions.some((action) => !action)) {
    return recommendation;
  }
  return `${issue} ควร${joinThai(actions)}`;
}
