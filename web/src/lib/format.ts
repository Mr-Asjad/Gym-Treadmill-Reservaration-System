const hm = new Intl.DateTimeFormat(undefined, {
  hour: "2-digit",
  minute: "2-digit",
});
const hms = new Intl.DateTimeFormat(undefined, {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

const t12 = new Intl.DateTimeFormat(undefined, {
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});

export const clock = (iso: string) => hm.format(new Date(iso));
export const clockSec = (iso: string) => hms.format(new Date(iso));
export const time12 = (iso: string) => t12.format(new Date(iso));

export function machineLabel(id: string): string {
  const n = id.split("-").at(-1) ?? id;
  return `Reserved Treadmill ${n}`;
}

export function laneLabel(id: string): string {
  return `Lane ${id.split("-").at(-1) ?? id}`;
}

export function laneKey(id: string): "a" | "b" {
  return (id.split("-").at(-1) ?? "1") === "1" ? "a" : "b";
}

/** "in 40 min" / "in 2 hr" / "now" from an ISO start and a now-ms. */
export function relStart(iso: string, nowMs: number): string {
  const mins = Math.round((Date.parse(iso) - nowMs) / 60000);
  if (mins <= 0) return "now";
  if (mins < 60) return `in ${mins} min`;
  const hr = Math.floor(mins / 60);
  const rem = mins % 60;
  return rem ? `in ${hr} hr ${rem} min` : `in ${hr} hr`;
}

export function machineIndex(id: string): string {
  const n = id.split("-").at(-1) ?? "0";
  return n.padStart(2, "0");
}

export function firstName(full: string | null): string {
  return full ? full.split(" ")[0] : "";
}
