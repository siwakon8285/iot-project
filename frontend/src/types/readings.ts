export type RoomStatus = "GOOD" | "MODERATE" | "HOT" | string;

export interface ReadingData {
  device_id: string;
  temperature: number;
  humidity: number;
  co2: number | null;
  fan_on: boolean;
}

export interface LatestReadingResponse {
  success: boolean;
  status: RoomStatus;
  recommendation: string;
  data: ReadingData;
}

export interface HistoryReading extends ReadingData {
  id: number;
  status: RoomStatus;
  recommendation: string;
  created_at: string;
}
