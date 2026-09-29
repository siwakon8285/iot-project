import { localizeRecommendation } from "../lib/recommendationLocale";

interface StatusCardProps {
  status: string;
  recommendation: string;
}

function getStatusClass(status: string): string {
  const normalizedStatus = status.toLowerCase();
  return ["good", "moderate", "hot"].includes(normalizedStatus)
    ? normalizedStatus
    : "unknown";
}

function getStatusLabel(status: string): string {
  switch (status) {
    case "GOOD": return "สภาพแวดล้อมเหมาะสม";
    case "MODERATE": return "ควรเฝ้าระวัง";
    case "HOT": return "ควรปรับสภาพแวดล้อม";
    default: return "ยังไม่ทราบสถานะ";
  }
}

export function StatusCard({ status, recommendation }: StatusCardProps) {
  const statusClass = getStatusClass(status);

  return (
    <article className={`status-card status-card--${statusClass}`}>
      <div className="status-card__heading">
        <div>
          <p className="section-kicker">สถานะสภาพแวดล้อม</p>
          <h2>การประเมินสภาพแวดล้อม</h2>
        </div>
        <span className="status-card__source">ข้อมูลจาก API</span>
      </div>
      <div className="status-card__content">
        <div className="status-card__badge">
          <span className="status-card__indicator" aria-hidden="true" />
          {getStatusLabel(status)}
        </div>
        <p className="status-card__recommendation">{localizeRecommendation(recommendation)}</p>
      </div>
    </article>
  );
}
