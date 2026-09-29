import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { HistoryChart, type ChartPoint } from "./components/HistoryChart";
import { AiAssessmentCard } from "./components/AiAssessmentCard";
import { MetricCard } from "./components/MetricCard";
import { ProfileModal } from "./components/ProfileModal";
import { StatusCard } from "./components/StatusCard";
import { ApiError, getAiAssessment, getLatestReading, getReadingHistory } from "./lib/api";
import { readSessionProfile, writeSessionProfile } from "./lib/profile";
import type { AiAssessmentResponse, Sensitivity } from "./types/ai";
import type { HistoryReading, LatestReadingResponse } from "./types/readings";

const POLL_INTERVAL_MS = 5_000;

function formatTimestamp(timestamp: string | undefined, includeDate = false): string {
  if (!timestamp) {
    return "รอข้อมูล";
  }

  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return "ไม่ทราบเวลา";
  }

  return new Intl.DateTimeFormat("th-TH", {
    month: includeDate ? "short" : undefined,
    day: includeDate ? "numeric" : undefined,
    hour: "2-digit",
    minute: "2-digit",
    second: includeDate ? "2-digit" : undefined,
  }).format(date);
}

function formatChartLabel(timestamp: string): string {
  return formatTimestamp(timestamp, true);
}

function sortChronologically(readings: HistoryReading[]): HistoryReading[] {
  return [...readings].sort((first, second) => {
    const firstTime = Date.parse(first.created_at);
    const secondTime = Date.parse(second.created_at);

    if (Number.isNaN(firstTime)) {
      return 1;
    }
    if (Number.isNaN(secondTime)) {
      return -1;
    }
    return firstTime - secondTime;
  });
}

function toChartPoints(
  readings: HistoryReading[],
  value: (reading: HistoryReading) => number | null,
): ChartPoint[] {
  return readings.map((reading) => ({
    timestamp: reading.created_at,
    label: formatChartLabel(reading.created_at),
    value: value(reading),
  }));
}

function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 0) {
    return "เชื่อมต่อ API ไม่ได้ กรุณาตรวจสอบว่า FastAPI กำลังทำงาน";
  }
  return "ยังโหลดข้อมูลจาก API ไม่สำเร็จ";
}

function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

export default function App() {
  const [latestReading, setLatestReading] = useState<LatestReadingResponse | null>(null);
  const [history, setHistory] = useState<HistoryReading[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [profile, setProfile] = useState<Sensitivity[] | null>(readSessionProfile);
  const [profileModalOpen, setProfileModalOpen] = useState(profile === null);
  const [aiResponse, setAiResponse] = useState<AiAssessmentResponse | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState(false);
  const [aiRequestNonce, setAiRequestNonce] = useState(0);
  const fetchingRef = useRef(false);
  const mountedRef = useRef(false);

  const closeProfileModal = useCallback(() => setProfileModalOpen(false), []);

  function confirmProfile(selection: Sensitivity[]) {
    if (selection.length === 0) {
      return;
    }
    writeSessionProfile(selection);
    setProfile([...selection]);
    setProfileModalOpen(false);
  }

  const refreshData = useCallback(async (initialLoad = false) => {
    if (fetchingRef.current) {
      return;
    }

    fetchingRef.current = true;
    if (initialLoad) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }

    const [latestResult, historyResult] = await Promise.allSettled([
      getLatestReading(),
      getReadingHistory(50),
    ]);

    if (mountedRef.current) {
      const errors: string[] = [];

      if (latestResult.status === "fulfilled") {
        setLatestReading(latestResult.value);
      } else if (!isNotFound(latestResult.reason)) {
        errors.push(`ค่าปัจจุบัน: ${getErrorMessage(latestResult.reason)}`);
      }

      if (historyResult.status === "fulfilled") {
        setHistory(historyResult.value);
      } else {
        errors.push(`ประวัติ: ${getErrorMessage(historyResult.reason)}`);
      }

      setError(errors.length ? errors.join(" ") : null);
      setLoading(false);
      setRefreshing(false);
    }

    fetchingRef.current = false;
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    void refreshData(true);

    const intervalId = window.setInterval(() => {
      void refreshData(false);
    }, POLL_INTERVAL_MS);

    return () => {
      mountedRef.current = false;
      window.clearInterval(intervalId);
    };
  }, [refreshData]);

  const current = latestReading?.data ?? null;
  const chronologicalHistory = useMemo(() => sortChronologically(history), [history]);
  const newestHistoryReading = chronologicalHistory[chronologicalHistory.length - 1];
  const hasAnyData = Boolean(current) || history.length > 0;
  const deviceId = current?.device_id ?? newestHistoryReading?.device_id ?? null;

  useEffect(() => {
    if (!profile || !deviceId) {
      return;
    }
    const controller = new AbortController();
    setAiResponse(null);
    setAiError(false);
    setAiLoading(true);
    // A short deferred start prevents React StrictMode's development effect
    // replay from sending two provider requests for one profile.
    const startId = window.setTimeout(() => {
      void getAiAssessment({ device_id: deviceId, sensitivities: profile }, controller.signal)
        .then((response) => {
          if (controller.signal.aborted) return;
          setAiResponse(response);
          setAiLoading(false);
        })
        .catch(() => {
          if (controller.signal.aborted) return;
          setAiError(true);
          setAiLoading(false);
        });
    }, 0);

    return () => {
      window.clearTimeout(startId);
      controller.abort();
    };
  }, [profile, deviceId, aiRequestNonce]);

  const temperaturePoints = useMemo(
    () => toChartPoints(chronologicalHistory, (reading) => reading.temperature),
    [chronologicalHistory],
  );
  const humidityPoints = useMemo(
    () => toChartPoints(chronologicalHistory, (reading) => reading.humidity),
    [chronologicalHistory],
  );
  const co2Points = useMemo(
    () => toChartPoints(chronologicalHistory, (reading) => reading.co2),
    [chronologicalHistory],
  );

  const connectionLabel = error
    ? "การเชื่อมต่อขัดข้อง"
    : loading
      ? "กำลังเชื่อมต่อ"
      : refreshing
        ? "กำลังอัปเดต"
        : "สด";
  const connectionClass = error ? "warning" : loading ? "connecting" : "connected";

  return (
    <main className="app-shell">
      <div className="dashboard">
        <header className="dashboard-header">
          <div className="brand-block">
            <div className="brand-mark" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
            <div>
              <p className="eyebrow">แดชบอร์ดข้อมูลสภาพแวดล้อม</p>
              <h1>AI Smart Health Environment</h1>
              <p className="device-line">
                Device ID · <strong>{deviceId ?? "รอข้อมูลจากอุปกรณ์"}</strong>
              </p>
            </div>
          </div>
          <div className="header-actions">
            {profile && (
              <button className="profile-edit-button" type="button" onClick={() => setProfileModalOpen(true)}>
                แก้ไขข้อมูลสุขภาพ
              </button>
            )}
            <div className={`connection-status connection-status--${connectionClass}`} aria-live="polite">
              <span className="connection-status__dot" aria-hidden="true" />
              {connectionLabel}
            </div>
            <button
              className="refresh-button"
              type="button"
              onClick={() => void refreshData(!hasAnyData)}
              disabled={refreshing || loading}
            >
              <span aria-hidden="true">↻</span>
              รีเฟรช
            </button>
          </div>
        </header>

        {error && (
          <div className="connection-alert" role="alert">
            <span className="connection-alert__icon" aria-hidden="true">!</span>
            <div>
              <strong>ยังอัปเดตข้อมูลบางส่วนไม่ได้</strong>
              <span>
                {hasAnyData ? " กำลังแสดงข้อมูลล่าสุดที่มีอยู่ " : " "}
                {error}
              </span>
            </div>
          </div>
        )}

        {loading && !hasAnyData ? (
          <section className="state-card" aria-live="polite">
            <div className="state-card__spinner" aria-hidden="true" />
            <p className="section-kicker">กำลังเชื่อมต่อ FastAPI</p>
            <h2>กำลังโหลดข้อมูลสภาพแวดล้อม</h2>
            <p>รอค่าที่วัดได้ล่าสุดจากอุปกรณ์</p>
          </section>
        ) : !hasAnyData ? (
          <section className="state-card state-card--empty" aria-live="polite">
            <div className="state-card__symbol" aria-hidden="true">⌁</div>
            <p className="section-kicker">ยังไม่มีข้อมูล</p>
            <h2>รอข้อมูลสภาพแวดล้อม</h2>
            <p>เมื่อ ESP32 ส่งค่าที่วัดได้ ข้อมูลจะปรากฏที่นี่โดยอัตโนมัติ</p>
            <button
              className="state-card__button"
              type="button"
              onClick={() => void refreshData(true)}
              disabled={loading || refreshing}
            >
              ลองอีกครั้ง
            </button>
          </section>
        ) : (
          <>
            <section className="section-block" aria-labelledby="current-reading-title">
              <div className="section-heading">
                <div>
                  <p className="section-kicker">ข้อมูลล่าสุด</p>
                  <h2 id="current-reading-title">ค่าปัจจุบัน</h2>
                </div>
                <span className="section-meta">อัปเดตอัตโนมัติทุก 5 วินาที</span>
              </div>
              {current ? (
                <div className="metric-grid">
                  <MetricCard
                    label="อุณหภูมิ"
                    value={current.temperature.toFixed(1)}
                    unit="°C"
                    detail="อุณหภูมิสภาพแวดล้อม"
                    tone="cyan"
                  />
                  <MetricCard
                    label="ความชื้น"
                    value={current.humidity.toFixed(1)}
                    unit="%RH"
                    detail="ความชื้นสัมพัทธ์"
                    tone="violet"
                  />
                  <MetricCard
                    label="CO₂"
                    value={current.co2 === null ? "รอข้อมูลเซนเซอร์" : current.co2.toFixed(0)}
                    unit={current.co2 === null ? undefined : "ppm"}
                    detail={current.co2 === null ? "ยังไม่มีค่าจาก SCD40" : "คาร์บอนไดออกไซด์"}
                    tone="amber"
                  />
                  <MetricCard
                    label="พัดลม"
                    value={current.fan_on ? "เปิด" : "ปิด"}
                    detail="สถานะรีเลย์อัตโนมัติ"
                    tone={current.fan_on ? "green" : "slate"}
                  />
                  <MetricCard
                    label="อัปเดตล่าสุด"
                    value={formatTimestamp(newestHistoryReading?.created_at)}
                    detail="จากประวัติข้อมูลที่บันทึกไว้"
                    tone="slate"
                  />
                </div>
              ) : (
                <div className="inline-empty">ยังแสดงค่าปัจจุบันไม่ได้ แต่คุณยังดูข้อมูลย้อนหลังด้านล่างได้</div>
              )}
            </section>

            {current && (
              <StatusCard
                status={latestReading?.status ?? "UNKNOWN"}
                recommendation={latestReading?.recommendation ?? "ยังไม่มีคำแนะนำ"}
              />
            )}

            {profile && (
              <AiAssessmentCard
                response={aiResponse}
                loading={aiLoading}
                error={aiError}
                hasDevice={deviceId !== null}
                onRetry={() => setAiRequestNonce((value) => value + 1)}
              />
            )}

            <section className="section-block history-section" aria-labelledby="history-title">
              <div className="section-heading">
                <div>
                  <p className="section-kicker">ข้อมูลที่บันทึกไว้</p>
                  <h2 id="history-title">ประวัติข้อมูลสภาพแวดล้อม</h2>
                </div>
                <span className="section-meta">{history.length} รายการ</span>
              </div>
              <div className="charts-grid">
                <HistoryChart
                  title="อุณหภูมิ"
                  description="อุณหภูมิสภาพแวดล้อมตามเวลา"
                  unit="°C"
                  color="#52d7ff"
                  data={temperaturePoints}
                  emptyMessage="รอข้อมูลอุณหภูมิ"
                />
                <HistoryChart
                  title="ความชื้น"
                  description="ความชื้นสัมพัทธ์ตามเวลา"
                  unit="%RH"
                  color="#a78bfa"
                  data={humidityPoints}
                  emptyMessage="รอข้อมูลความชื้น"
                />
                <HistoryChart
                  title="CO₂"
                  description="แสดงค่าจาก SCD40 เมื่อมีข้อมูล"
                  unit="ppm"
                  color="#f8bd62"
                  data={co2Points}
                  emptyMessage="รอข้อมูลเซนเซอร์"
                />
              </div>
            </section>
          </>
        )}

        {profile && !hasAnyData && (
          <AiAssessmentCard
            response={aiResponse}
            loading={aiLoading}
            error={aiError}
            hasDevice={deviceId !== null}
            onRetry={() => setAiRequestNonce((value) => value + 1)}
          />
        )}

        <footer className="dashboard-footer">
          <span>แสดงข้อมูลเท่านั้น · ESP32 ควบคุมพัดลมอัตโนมัติ</span>
          <span>AI Smart Health Environment</span>
        </footer>
      </div>
      {profileModalOpen && (
        <ProfileModal
          initialSelection={profile ?? []}
          canDismiss={profile !== null}
          onConfirm={confirmProfile}
          onClose={closeProfileModal}
        />
      )}
    </main>
  );
}
