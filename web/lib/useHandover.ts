"use client";

/**
 * One handover session: the snapshot, the event stream, and the actions a clinician can take.
 *
 * Every action posts to the sidecar and adopts the snapshot that comes back, so the screen can
 * never show a fact in a state the engine did not put it in. The event stream is what makes the
 * screen move on its own — a barge-in recorded by the agent shows up here without a poll.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, EVENT_TYPES, HearbackEvent, Relay, Snapshot, api, speechDurationMs } from "./api";

export type Connection = "connecting" | "live" | "offline";

export interface Handover {
  sessionId: string | null;
  snapshot: Snapshot | null;
  events: HearbackEvent[];
  relay: Relay | null;
  connection: Connection;
  error: string | null;
  busy: boolean;
  say: (text: string) => Promise<void>;
  deliver: (interruptedAtMs?: number) => Promise<void>;
  verify: (field: string) => Promise<void>;
  resolve: (field: string, value: string) => Promise<void>;
  buildRelay: (lang: "en" | "hi") => Promise<void>;
  setProvider: (provider: string, reason: string) => Promise<void>;
  setToolDelay: (delayMs: number) => Promise<void>;
}

export function useHandover(): Handover {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [events, setEvents] = useState<HearbackEvent[]>([]);
  const [relay, setRelay] = useState<Relay | null>(null);
  const [connection, setConnection] = useState<Connection>("connecting");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const session = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .createSession()
      .then((body) => {
        if (cancelled || !body.session_id) return;
        session.current = body.session_id;
        setSessionId(body.session_id);
        setSnapshot(body);
      })
      .catch((exc: unknown) => {
        if (!cancelled) {
          setConnection("offline");
          setError(describe(exc));
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // The stream is the only thing that moves the screen without a click, so a dropped connection
  // has to be visible rather than silently leaving a stale board on the wall.
  useEffect(() => {
    if (!sessionId) return;
    const source = new EventSource(api.eventsUrl(sessionId));
    const onEvent = (raw: MessageEvent<string>) => {
      const event = JSON.parse(raw.data) as HearbackEvent;
      setEvents((previous) =>
        previous.some((e) => e.seq === event.seq) ? previous : [...previous, event],
      );
      api.state(sessionId).then(setSnapshot).catch(() => undefined);
    };
    source.onopen = () => {
      setConnection("live");
      setError(null);
    };
    source.onerror = () => setConnection("offline");
    for (const type of EVENT_TYPES) source.addEventListener(type, onEvent as EventListener);
    return () => source.close();
  }, [sessionId]);

  const act = useCallback(
    async (work: (id: string) => Promise<Snapshot>) => {
      const id = session.current;
      if (!id) return;
      setBusy(true);
      try {
        const body = await work(id);
        setSnapshot(body);
        if (body.relay) setRelay(body.relay);
        setError(body.error ?? null);
      } catch (exc: unknown) {
        setError(describe(exc));
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  /**
   * One turn: open a new epoch, settle any read-back it confirms, then extract into it.
   *
   * Whether the turn was a confirmation is the sidecar's verdict, not a regular expression
   * repeated here — the same call the voice agent makes when the paramedic says "yes".
   */
  const say = useCallback(
    async (text: string) =>
      act(async (id) => {
        const opened = await api.utterance(id, text);
        let latest = opened;
        const refused: string[] = [];
        if (opened.confirmation?.affirmation) {
          for (const field of opened.awaiting_confirmation) {
            latest = await api.verify(id, field, text);
            if (latest.verified === false && latest.challenge) refused.push(latest.challenge);
          }
        }
        const extracted = await api.extract(id, text, latest.state.epoch);
        // A refused confirmation is the product working, not an error — but it has to be seen,
        // because the clinician believes that value is now agreed.
        return refused.length ? { ...extracted, error: refused.join("; ") } : extracted;
      }),
    [act],
  );

  /**
   * Simulate the agent speaking its next line, optionally cut off partway through.
   * The real agent posts the same call with Rime's word timestamps instead of an estimate.
   */
  const deliver = useCallback(
    async (interruptedAtMs?: number) =>
      act(async (id) => {
        const line = snapshot?.next_line;
        if (!line) throw new Error("there is no line waiting to be spoken");
        const duration = speechDurationMs(line.plain);
        let latest = snapshot!;
        for (const field of line.fields) {
          latest = await api.delivery(
            id,
            field,
            latest.state.epoch,
            line.plain,
            duration,
            interruptedAtMs,
          );
        }
        return latest;
      }),
    [act, snapshot],
  );

  const verify = useCallback((field: string) => act((id) => api.verify(id, field)), [act]);

  const resolve = useCallback(
    (field: string, value: string) => act((id) => api.resolve(id, field, value)),
    [act],
  );

  const buildRelay = useCallback(
    (lang: "en" | "hi") => act((id) => api.relay(id, lang)),
    [act],
  );

  const setProvider = useCallback(
    (provider: string, reason: string) => act((id) => api.provider(id, provider, reason)),
    [act],
  );

  const setToolDelay = useCallback(
    (delayMs: number) => act((id) => api.toolDelay(id, delayMs)),
    [act],
  );

  return {
    sessionId,
    snapshot,
    events,
    relay,
    connection,
    error,
    busy,
    say,
    deliver,
    verify,
    resolve,
    buildRelay,
    setProvider,
    setToolDelay,
  };
}

function describe(exc: unknown): string {
  if (exc instanceof ApiError) return `${exc.status}: ${exc.message}`;
  if (exc instanceof Error) return exc.message;
  return String(exc);
}
