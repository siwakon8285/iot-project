import type { AiAssessmentResponse, AiSuitability } from "../types/ai";

interface AiAssessmentCardProps {
  response: AiAssessmentResponse | null;
  loading: boolean;
  error: boolean;
  hasDevice: boolean;
  onRetry: () => void;
}

const suitabilityLabels: Record<AiSuitability, string> = {
  SUITABLE: "เหมาะสม",
  CAUTION: "ควรเฝ้าระวัง",
  NOT_SUITABLE: "อาจไม่เหมาะกับคุณ",
};

export function AiAssessmentCard({
  response,
  loading,
  error,
  hasDevice,
  onRetry,
}: AiAssessmentCardProps) {
  const assessment = response?.assessment;

  return (
    <section className="ai-card section-block" aria-labelledby="ai-assessment-title">
      <div className="ai-card__header">
        <div>
          <p className="section-kicker">ผู้ช่วย AI</p>
          <h2 id="ai-assessment-title">AI วิเคราะห์สำหรับคุณ</h2>
          <p className="ai-card__subtitle">วิเคราะห์จากสภาพแวดล้อมปัจจุบันและข้อมูลสุขภาพที่คุณเลือก</p>
        </div>
        <button className="ai-card__refresh" type="button" onClick={onRetry} disabled={loading || !hasDevice}>
          วิเคราะห์อีกครั้ง
        </button>
      </div>

      <div aria-live="polite">
        {loading ? (
          <div className="ai-card__state">
            <span className="ai-card__spinner" aria-hidden="true" />
            <p>AI กำลังวิเคราะห์สภาพแวดล้อมสำหรับคุณ...</p>
          </div>
        ) : error ? (
          <div className="ai-card__state ai-card__state--error" role="alert">
            <p>ยังไม่สามารถวิเคราะห์ข้อมูลสำหรับคุณได้ในขณะนี้ กรุณาลองใหม่อีกครั้ง</p>
            <button className="ai-card__retry" type="button" onClick={onRetry} disabled={!hasDevice}>ลองวิเคราะห์อีกครั้ง</button>
          </div>
        ) : assessment ? (
          <div className="ai-card__result">
            <span className={`ai-card__badge ai-card__badge--${assessment.suitability.toLowerCase()}`}>
              {suitabilityLabels[assessment.suitability]}
            </span>
            <h3>{assessment.title}</h3>
            <p className="ai-card__summary">{assessment.summary}</p>
            <div className="ai-card__details">
              <div className="ai-card__list-block">
                <h4>เหตุผลที่ควรสังเกต</h4>
                <ul>{assessment.reasons.map((reason, index) => <li key={`${index}-${reason}`}>{reason}</li>)}</ul>
              </div>
              <div className="ai-card__list-block">
                <h4>คำแนะนำสำหรับคุณ</h4>
                <ul>{assessment.recommendations.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul>
              </div>
            </div>
            <p className="ai-card__disclaimer">{response.disclaimer}</p>
          </div>
        ) : (
          <div className="ai-card__state">
            <p>{hasDevice ? "เลือกข้อมูลสุขภาพเพื่อเริ่มวิเคราะห์สภาพแวดล้อม" : "รอข้อมูลจากอุปกรณ์เพื่อเริ่มวิเคราะห์สภาพแวดล้อม"}</p>
          </div>
        )}
      </div>
    </section>
  );
}
