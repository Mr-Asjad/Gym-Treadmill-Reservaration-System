import type { FloorMachine, Verdict } from "../lib/api";
import { clock, clockSec, machineIndex, machineLabel } from "../lib/format";

const TONE: Record<Verdict, "live" | "warn" | "alert" | "clay" | ""> = {
  on_machine: "live",
  reserved_soon: "clay",
  nudge: "warn",
  waiting: "warn",
  no_show: "alert",
  unbooked_use: "clay",
  idle: "",
  no_camera: "",
};

export function MachineCard({ m }: { m: FloorMachine }) {
  const tone = TONE[m.verdict];
  const camera =
    m.camera.occupied == null
      ? "no signal"
      : m.camera.occupied
        ? "occupied"
        : "clear";

  return (
    <article className="mcard" data-tone={tone || undefined}>
      <div className="idx">{machineIndex(m.machine_id)}</div>
      <h2>{machineLabel(m.machine_id)}</h2>

      <div className="status-line">
        <span className="dot" aria-hidden="true" />
        {m.headline}
      </div>

      <dl>
        <dt>Reservation</dt>
        <dd>
          {m.window
            ? `${m.member_name}, ${clock(m.window[0])} to ${clock(m.window[1])}`
            : "none"}
        </dd>
        <dt>Camera</dt>
        <dd>
          {camera}
          {m.camera.occupied && m.camera.since && (
            <span className="muted tnum"> · since {clockSec(m.camera.since)}</span>
          )}
        </dd>
      </dl>
    </article>
  );
}
