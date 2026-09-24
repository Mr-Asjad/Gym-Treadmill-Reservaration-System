import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, type Member, type SlotRow, type Suggestion } from "../lib/api";
import { firstName, laneLabel, relStart, time12 } from "../lib/format";
import { Bolt, Check, Close } from "../components/icons";

type Flash = { kind: "ok" | "err"; text: string } | null;
type Day = "today" | "tomorrow";

const HALF_HOUR = 30 * 60 * 1000;
const plus30 = (iso: string) => new Date(Date.parse(iso) + HALF_HOUR).toISOString();

const FRIENDLY: Record<string, string> = {
  member_not_premium: "Reserved Row is a premium perk. Pick a premium member to try it.",
  slot_unavailable: "Ah, someone grabbed that one first.",
  machine_not_reservable: "That lane isn't reservable.",
  invalid_window: "That slot has already started.",
};

function useNow(ms = 20000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(t);
  }, [ms]);
  return now;
}

export function Book() {
  const [members, setMembers] = useState<Member[]>([]);
  const [memberId, setMemberId] = useState("");
  const [day, setDay] = useState<Day>("today");
  const [rows, setRows] = useState<SlotRow[] | null>(null);
  const [next, setNext] = useState<Suggestion | null>(null);
  const [flash, setFlash] = useState<Flash>(null);
  const [busy, setBusy] = useState(false);
  const [popped, setPopped] = useState<string | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const now = useNow();
  const flashTimer = useRef<number | undefined>(undefined);

  const member = useMemo(
    () => members.find((m) => m.id === memberId),
    [members, memberId],
  );
  const premium = !!member?.is_premium;

  useEffect(() => {
    api.members().then((ms) => {
      setMembers(ms);
      setMemberId(ms.find((m) => m.is_premium)?.id ?? ms[0]?.id ?? "");
    });
  }, []);

  const refresh = useCallback(async () => {
    if (!memberId) return;
    const [slots, sug] = await Promise.allSettled([
      api.slots(memberId, day),
      day === "today" && premium
        ? api.suggest(memberId, 30)
        : Promise.resolve(null),
    ]);
    if (slots.status === "fulfilled") setRows(slots.value);
    else setFlash({ kind: "err", text: "Couldn't load the schedule." });
    setNext(sug.status === "fulfilled" ? sug.value : null);
  }, [memberId, day, premium]);

  useEffect(() => {
    setRows(null);
    refresh();
  }, [refresh]);

  function say(f: Flash) {
    setFlash(f);
    window.clearTimeout(flashTimer.current);
    if (f) flashTimer.current = window.setTimeout(() => setFlash(null), 4000);
  }
  const fail = (e: unknown) => {
    const err = e as ApiError;
    say({ kind: "err", text: FRIENDLY[err.code] ?? err.message });
  };

  async function book(machineId: string, startIso: string) {
    setBusy(true);
    try {
      await api.createBooking({
        machine_id: machineId,
        member_id: memberId,
        start: startIso,
        end: plus30(startIso),
      });
      setPopped(`${machineId}:${startIso}`);
      setTimeout(() => setPopped(null), 700);
      say({ kind: "ok", text: `Locked in. ${laneLabel(machineId)} at ${time12(startIso)}.` });
      await refresh();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }

  async function cancel(bookingId: string) {
    setBusy(true);
    try {
      await api.cancelBooking(bookingId);
      say({ kind: "ok", text: "Released. Back in the pool." });
      await refresh();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
      setConfirmId(null);
    }
  }

  function tapMine(bookingId: string) {
    if (confirmId === bookingId) {
      cancel(bookingId);
    } else {
      setConfirmId(bookingId);
      setTimeout(() => setConfirmId((c) => (c === bookingId ? null : c)), 3000);
    }
  }

  const nowRowIdx = rows
    ? rows.findIndex((r) => Date.parse(r.start) > now)
    : -1;

  return (
    <div className="book">
      <div className="greet">
        <span className="hi">
          Hey{member ? ` ${firstName(member.name)}` : " there"}
          <span className="wave" aria-hidden="true">
            👋
          </span>
        </span>
        <h1>Grab a lane.</h1>

        <span className="whoami-label">booking as</span>
        <div className="whoami" role="group" aria-label="Booking as">
          {members.map((m) => (
            <button
              key={m.id}
              aria-pressed={m.id === memberId}
              className={m.is_premium ? "" : "basic"}
              onClick={() => setMemberId(m.id)}
            >
              {firstName(m.name)}
            </button>
          ))}
        </div>
      </div>

      {flash && <div className={`flash ${flash.kind}`}>{flash.text}</div>}

      {day === "today" && premium && next && (
        <button
          className="grab"
          disabled={busy}
          onClick={() => book(next.machine_id, next.start)}
        >
          <span>
            <span className="kicker">Next free lane</span>
            <span className="headline">
              {laneLabel(next.machine_id)}, {time12(next.start)}
            </span>
            <span className="sub">
              {relStart(next.start, now)} · one tap and it's yours
            </span>
          </span>
          <span className="go">
            <span className="bolt">
              <Bolt size={22} />
            </span>
          </span>
        </button>
      )}

      {!premium && member && (
        <div className="flash err">
          {firstName(member.name)} is on the basic plan. Reserved Row is
          premium-only, but you can still look around.
        </div>
      )}

      <div className="or">or pick your time</div>

      <div className="segmented daytabs" role="group" aria-label="Day">
        <button aria-pressed={day === "today"} onClick={() => setDay("today")}>
          Today
        </button>
        <button
          aria-pressed={day === "tomorrow"}
          onClick={() => setDay("tomorrow")}
        >
          Tomorrow
        </button>
      </div>

      {rows === null && (
        <div className="timeline">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="skel" style={{ opacity: 1 - i * 0.14 }} />
          ))}
        </div>
      )}

      {rows?.length === 0 && (
        <div className="done">
          <h3>{day === "today" ? "That's a wrap for today." : "Nothing here yet."}</h3>
          <p>
            {day === "today"
              ? "Every lane's done for the day."
              : "Tomorrow hasn't opened up."}
          </p>
          {day === "today" && (
            <button className="btn btn-ghost" onClick={() => setDay("tomorrow")}>
              See tomorrow
            </button>
          )}
        </div>
      )}

      {rows && rows.length > 0 && (
        <div className="timeline">
          {nowRowIdx === 0 && (
            <div className="nowline">
              <span className="pip" /> now
            </div>
          )}
          {rows.map((row, i) => (
            <div key={row.start}>
              <div className="slotrow" style={{ "--i": i } as React.CSSProperties}>
                <div className="time tnum">{time12(row.start)}</div>
                <div className="lanes">
                  {row.cells.map((cell) => {
                    const key = `${cell.machine_id}:${row.start}`;
                    const pop = popped === key;
                    if (cell.state === "open") {
                      return (
                        <button
                          key={cell.machine_id}
                          className={`slot open${pop ? " pop" : ""}`}
                          disabled={busy || !premium}
                          onClick={() => book(cell.machine_id, row.start)}
                        >
                          <span className="lane">{laneLabel(cell.machine_id)}</span>
                          <span className="who">Open</span>
                          {pop && (
                            <span className="spark" aria-hidden="true">
                              <i /><i /><i /><i /><i />
                            </span>
                          )}
                        </button>
                      );
                    }
                    if (cell.state === "mine") {
                      const confirming = confirmId === cell.booking_id;
                      return (
                        <button
                          key={cell.machine_id}
                          className={`slot mine${confirming ? " confirm" : ""}${pop ? " pop" : ""}`}
                          disabled={busy}
                          onClick={() =>
                            cell.booking_id && tapMine(cell.booking_id)
                          }
                        >
                          <span className="lane">{laneLabel(cell.machine_id)}</span>
                          <span className="who">
                            {confirming ? "Cancel?" : "You're in"}
                          </span>
                          <span className="corner">
                            {confirming ? <Close size={16} /> : <Check size={16} />}
                          </span>
                          {pop && (
                            <span className="spark" aria-hidden="true">
                              <i /><i /><i /><i /><i />
                            </span>
                          )}
                        </button>
                      );
                    }
                    if (cell.state === "past") {
                      return (
                        <div key={cell.machine_id} className="slot past">
                          <span className="lane">{laneLabel(cell.machine_id)}</span>
                          <span className="who">closed</span>
                        </div>
                      );
                    }
                    return (
                      <div key={cell.machine_id} className="slot booked">
                        <span className="lane">{laneLabel(cell.machine_id)}</span>
                        <span className="who">{firstName(cell.member_name)}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
              {nowRowIdx === i + 1 && (
                <div className="nowline" style={{ marginTop: "var(--s3)" }}>
                  <span className="pip" /> now
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {rows && rows.length > 0 && (
        <p
          className="muted"
          style={{
            textAlign: "center",
            fontSize: "var(--step--1)",
            fontWeight: 600,
            marginTop: "var(--s6)",
          }}
        >
          Show up within the grace window or the lane opens back up.
        </p>
      )}
    </div>
  );
}
