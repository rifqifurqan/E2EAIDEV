// NFR-20: the API stores and returns UTC; the UI shows time in the user's zone (default Asia/Jakarta).
export const DEFAULT_TIME_ZONE = "Asia/Jakarta";

const HAS_OFFSET = /(Z|[+-]\d{2}:?\d{2})$/i;

function validZone(zone: string | null | undefined): string {
  if (!zone) return DEFAULT_TIME_ZONE;
  try {
    new Intl.DateTimeFormat("en", { timeZone: zone });
    return zone;
  } catch {
    return DEFAULT_TIME_ZONE;
  }
}

export function formatTimestamp(
  value: string | null | undefined,
  timeZone?: string | null,
  locale: "en" | "id" = "en",
): string {
  if (!value) return "—";
  const date = new Date(HAS_OFFSET.test(value) ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) return "—";
  const parts = new Intl.DateTimeFormat(locale === "id" ? "id-ID" : "en-GB", {
    timeZone: validZone(timeZone),
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("day")} ${get("month")} ${get("year")}, ${get("hour")}:${get("minute")}`;
}
