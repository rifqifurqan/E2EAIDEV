"use client";

import { useEffect, useState } from "react";
import { ApiError } from "./api-client";

export type LoadState<T> =
  | { kind: "loading" }
  | { kind: "ready"; data: T }
  | { kind: "forbidden" }
  | { kind: "error" };

/** Loads admin-scoped data once; maps 401/403 to "forbidden" so screens never crash. */
export function useAdminData<T>(load: () => Promise<T>): LoadState<T> {
  const [state, setState] = useState<LoadState<T>>({ kind: "loading" });
  useEffect(() => {
    let cancelled = false;
    load().then(
      (data) => {
        if (!cancelled) setState({ kind: "ready", data });
      },
      (error: unknown) => {
        if (cancelled) return;
        const forbidden = error instanceof ApiError && (error.status === 403 || error.status === 401);
        setState(forbidden ? { kind: "forbidden" } : { kind: "error" });
      },
    );
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return state;
}
