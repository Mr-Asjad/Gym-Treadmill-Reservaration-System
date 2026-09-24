// Typed client for the Reserved Row API. Shapes mirror api/schemas.py by hand.

export type Member = { id: string; name: string; is_premium: boolean };
export type Machine = { id: string; name: string };

export type SlotState = "open" | "booked" | "mine" | "past";
export type SlotCell = {
  machine_id: string;
  state: SlotState;
  booking_id: string | null;
  member_name: string | null;
};
export type SlotRow = { label: string; start: string; cells: SlotCell[] };

export type Booking = {
  id: string;
  machine_id: string;
  member_id: string;
  member_name: string;
  start: string;
  end: string;
  status: string;
};

export type Suggestion = {
  machine_id: string;
  start: string;
  end: string;
  wait_seconds: number;
};

export type Verdict =
  | "idle"
  | "unbooked_use"
  | "reserved_soon"
  | "nudge"
  | "on_machine"
  | "waiting"
  | "no_show"
  | "no_camera";

export type FloorMachine = {
  machine_id: string;
  machine_name: string;
  member_name: string | null;
  window: [string, string] | null;
  camera: { occupied: boolean | null; since: string | null };
  verdict: Verdict;
  headline: string;
};

export type Adherence = {
  total: number;
  honored: number;
  no_shows: number;
  cancelled: number;
  adherence_pct: number;
};

export type FiredEvent = {
  kind: string;
  machine_id: string;
  member_name: string;
  detail: string;
};

export type FloorState = {
  now: string;
  scheduler_mode: string;
  machines: FloorMachine[];
  adherence: Adherence;
  fired: FiredEvent[];
};

export type ActivityEvent = {
  at: string;
  type: string;
  label: string;
  machine_id: string | null;
  member_name: string | null;
};

export class ApiError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let code = String(res.status);
    let message = res.statusText;
    try {
      const body = await res.json();
      const d = body.detail;
      if (d && typeof d === "object") {
        code = d.code ?? code;
        message = d.message ?? message;
      } else if (typeof d === "string") {
        message = d;
      }
    } catch {
      /* keep defaults */
    }
    throw new ApiError(code, message);
  }
  return res.json() as Promise<T>;
}

export const api = {
  members: () => req<Member[]>("/members"),
  machines: () => req<Machine[]>("/machines"),
  slots: (memberId: string, day: "today" | "tomorrow") =>
    req<SlotRow[]>(`/slots?member_id=${encodeURIComponent(memberId)}&day=${day}`),
  createBooking: (b: {
    machine_id: string;
    member_id: string;
    start: string;
    end: string;
  }) => req<Booking>("/bookings", { method: "POST", body: JSON.stringify(b) }),
  cancelBooking: (id: string) =>
    req<Booking>(`/bookings/${id}`, { method: "DELETE" }),
  suggest: (member_id: string, duration_minutes = 30) =>
    req<Suggestion>("/bookings/suggest", {
      method: "POST",
      body: JSON.stringify({ member_id, duration_minutes }),
    }),
  floor: () => req<FloorState>("/floor"),
  activity: (limit = 15) => req<ActivityEvent[]>(`/activity?limit=${limit}`),
  sim: (machine_id: string, occupied: boolean) =>
    req<{ occupied: boolean | null; since: string | null }>("/sim/occupancy", {
      method: "POST",
      body: JSON.stringify({ machine_id, occupied }),
    }),
};
