"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Job, type JobType } from "./api";

/**
 * Async job hook (#53). Runs a long AI op server-side and survives navigation:
 * - start(params) creates a job + begins polling
 * - on mount, resumes any queued/running job of this type (so switching menus
 *   and coming back keeps showing progress)
 * - onDone(result) fires once when the job completes successfully
 *
 * Returns { job, running, start } — `running` is true while queued/running.
 */
export function useJob(jobType: JobType, onDone?: (result: any) => void) {
  const [job, setJob] = useState<Job | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const doneFired = useRef<string | null>(null);
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  const running = job?.status === "queued" || job?.status === "running";

  const stop = useCallback(() => {
    if (timer.current) { clearInterval(timer.current); timer.current = null; }
  }, []);

  const poll = useCallback(async (jobId: string) => {
    try {
      const j = await api.getJob(jobId);
      setJob(j);
      if (j.status === "done" || j.status === "failed") {
        stop();
        if (j.status === "done" && doneFired.current !== j.id) {
          doneFired.current = j.id;
          onDoneRef.current?.(j.result);
        }
      }
    } catch {
      // transient error — keep polling
    }
  }, [stop]);

  const beginPolling = useCallback((jobId: string) => {
    stop();
    poll(jobId);
    timer.current = setInterval(() => poll(jobId), 4000);
  }, [poll, stop]);

  const start = useCallback(async (params: Record<string, unknown>) => {
    const j = await api.startJob(jobType, params);
    setJob(j);
    doneFired.current = null;
    beginPolling(j.id);
    return j;
  }, [jobType, beginPolling]);

  // Resume an in-flight job of this type on mount.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const active = await api.listJobs(jobType);
        const inflight = active.find((j) => j.status === "queued" || j.status === "running");
        if (inflight && !cancelled) {
          setJob(inflight);
          beginPolling(inflight.id);
        }
      } catch { /* ignore */ }
    })();
    return () => { cancelled = true; stop(); };
  }, [jobType, beginPolling, stop]);

  return { job, running, start };
}
