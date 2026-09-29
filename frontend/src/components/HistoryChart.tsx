import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface ChartPoint {
  timestamp: string;
  label: string;
  value: number | null;
}

interface HistoryChartProps {
  title: string;
  description: string;
  unit: string;
  color: string;
  data: ChartPoint[];
  emptyMessage: string;
}

export function HistoryChart({
  title,
  description,
  unit,
  color,
  data,
  emptyMessage,
}: HistoryChartProps) {
  const hasValues = data.some(
    (point) => point.value !== null && Number.isFinite(point.value),
  );

  return (
    <article className="chart-card">
      <div className="chart-card__header">
        <div>
          <p className="section-kicker">ประวัติ</p>
          <h3>{title}</h3>
        </div>
        <span className="chart-card__unit">{unit}</span>
      </div>
      <p className="chart-card__description">{description}</p>
      <div className="chart-card__body">
        {!data.length || !hasValues ? (
          <div className="chart-empty">
            <span className="chart-empty__mark" aria-hidden="true">
              {data.length ? "—" : "…"}
            </span>
            <span>{data.length ? emptyMessage : "ยังไม่มีข้อมูล"}</span>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 4 }}>
              <CartesianGrid stroke="rgba(148, 163, 184, 0.14)" vertical={false} />
              <XAxis
                dataKey="label"
                tick={{ fill: "#8fa0b6", fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                minTickGap={34}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fill: "#8fa0b6", fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                width={unit === "ppm" ? 68 : 48}
                tickFormatter={(value) => `${Math.round(Number(value))} ${unit}`}
              />
              <Tooltip
                cursor={{ stroke: "rgba(148, 163, 184, 0.3)" }}
                contentStyle={{
                  background: "#142136",
                  border: "1px solid rgba(148, 163, 184, 0.22)",
                  borderRadius: "12px",
                  color: "#edf4ff",
                  boxShadow: "0 12px 32px rgba(0, 0, 0, 0.24)",
                }}
                labelStyle={{ color: "#9aaac0", marginBottom: "4px" }}
                formatter={(value) => [value === null ? "รอข้อมูลเซนเซอร์" : `${value} ${unit}`, title]}
              />
              <Line
                type="monotone"
                dataKey="value"
                stroke={color}
                strokeWidth={2.5}
                dot={false}
                activeDot={{ r: 4, fill: color, stroke: "#edf4ff", strokeWidth: 2 }}
                connectNulls={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </article>
  );
}
