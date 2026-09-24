import { useEffect, useRef, useState } from "react";
import { api, type ActivityEvent, type FloorState } from "../lib/api";
import { clockSec, machineLabel } from "../lib/format";
import { MachineCard } from "../components/MachineCard";
import { Toasts, type Toast } from "../components/Toasts";

export function Floor() {
  const [state, setState] = useState<FloorState | null>(null);
  const [activity, setActivity] = useState<ActivityEvent[]>([]);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const toastSeq = useRef(0);

  function pushToast(text: string, alert: boolean) {
    const id = ++toastSeq.current;
    setToasts((t) => [...t, { id, text, alert }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5000);
  }

  useEffect(() => {
    let alive = true;
    let poll: number | undefined;

    const ingest = (s: FloorState) => {
      if (!alive) return;
      setState(s);
      for (const f of s.fired) {
        pushToast(
          `${f.kind === "nudge" ? "Nudge" : "No-show"} · ${machineLabel(
            f.machine_id,
          )} — ${f.detail}`,
          f.kind !== "nudge",
        );
      }
      api.activity().then((a) => alive && setActivity(a));
    };

    // paint immediately, don't wait for the first SSE tick
    api.floor().then(ingest).catch(() => {});

    const es = new EventSource("/api/stream");
    es.onmessage = (e) => ingest(JSON.parse(e.data) as FloorState);
    es.onerror = () => {
      es.close();
      if (poll) return;
      poll = window.setInterval(async () => {
        ingest(await api.floor());
      }, 2000);
      api.floor().then(ingest);
    };

    return () => {
      alive = false;
      es.close();
      if (poll) clearInterval(poll);
    };
  }, []);

  async function toggleSim(machineId: string, occupied: boolean) {
    await api.sim(machineId, occupied);
  }

  const a = state?.adherence;

  return (
    <>
      <div className="page-head">
        <span className="eyebrow">Staff</span>
        <h1>The floor.</h1>
        <p>
          Live occupancy against the booked schedule. Nudges and no-show releases
          fire on their own. This view just watches.
        </p>
      </div>

      <div className="control-row" style={{ justifyContent: "space-between" }}>
        <span className="live-chip">
          <span className="dot" aria-hidden="true" />
          Live{state ? ` · ${clockSec(state.now)}` : ""}
        </span>
        {state && (
          <span className="muted" style={{ fontSize: "var(--step--1)", fontWeight: 600 }}>
            scheduler: {state.scheduler_mode}
          </span>
        )}
      </div>

      <div className="stat-strip">
        <div className="stat">
          <div className="k">Adherence</div>
          <div className="v tnum">{a ? `${a.adherence_pct.toFixed(0)}%` : "—"}</div>
        </div>
        <div className="stat">
          <div className="k">Honored</div>
          <div className="v tnum">{a ? `${a.honored}/${a.total}` : "—"}</div>
        </div>
        <div className="stat">
          <div className="k">No-shows</div>
          <div className="v tnum">{a?.no_shows ?? "—"}</div>
        </div>
        <div className="stat">
          <div className="k">Cancelled</div>
          <div className="v tnum">{a?.cancelled ?? "—"}</div>
        </div>
      </div>

      <div className="machines">
        {state?.machines.map((m) => (
          <MachineCard key={m.machine_id} m={m} />
        ))}
      </div>

      <div className="panel">
        <h3>Simulate camera</h3>
        <div className="sim">
          {state?.machines.map((m) => (
            <label className="toggle" key={m.machine_id}>
              <input
                type="checkbox"
                checked={m.camera.occupied === true}
                onChange={(e) => toggleSim(m.machine_id, e.target.checked)}
              />
              {machineLabel(m.machine_id)} — someone on it
            </label>
          ))}
        </div>
      </div>

      <div className="panel">
        <h3>Recent activity</h3>
        {activity.length === 0 ? (
          <ul className="activity">
            <li>
              <time>—</time>
              <span className="what muted">
                Nothing yet. Make a booking on the member view.
              </span>
            </li>
          </ul>
        ) : (
          <ul className="activity">
            {activity.map((e, i) => (
              <li key={`${e.at}-${i}`}>
                <time className="tnum">{clockSec(e.at)}</time>
                <span className={`what ${e.type}`}>
                  <b>{e.label}</b>
                  {e.machine_id ? ` · ${machineLabel(e.machine_id)}` : ""}
                  {e.member_name ? ` · ${e.member_name}` : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <Toasts items={toasts} />
    </>
  );
}
