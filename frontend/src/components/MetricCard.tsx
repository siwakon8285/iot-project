import type { ReactNode } from "react";

interface MetricCardProps {
  label: string;
  value: ReactNode;
  unit?: string;
  detail?: string;
  tone?: "cyan" | "violet" | "amber" | "green" | "slate";
}

export function MetricCard({
  label,
  value,
  unit,
  detail,
  tone = "cyan",
}: MetricCardProps) {
  return (
    <article className={`metric-card metric-card--${tone}`}>
      <div className="metric-card__topline">
        <span className="metric-card__label">{label}</span>
        <span className="metric-card__dot" aria-hidden="true" />
      </div>
      <div className="metric-card__value">
        {value}
        {unit && <span className="metric-card__unit">{unit}</span>}
      </div>
      {detail && <p className="metric-card__detail">{detail}</p>}
    </article>
  );
}
