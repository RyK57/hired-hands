"use client";

import { useEffect, useState } from "react";
import type { RealtimePostgresChangesPayload } from "@supabase/supabase-js";
import { supabase } from "./supabase";
import { PRIMARY_KEY, type TableName, type Tables } from "./types";

export interface LiveQuery {
  eq?: [column: string, value: string | number | boolean];
  order?: { column: string; ascending?: boolean };
  limit?: number;
  enabled?: boolean;
}

export interface LiveResult<T> {
  rows: T[];
  loading: boolean;
  error: string | null;
}

type AnyRow = Record<string, unknown>;

interface Snapshot {
  key: string;
  rows: AnyRow[];
  error: string | null;
  loaded: boolean;
}

const EMPTY: Snapshot = { key: "", rows: [], error: null, loaded: false };

let channelCounter = 0;

function compare(a: unknown, b: unknown): number {
  if (a === b) return 0;
  if (a === null || a === undefined) return 1;
  if (b === null || b === undefined) return -1;
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a) < String(b) ? -1 : 1;
}

function arrange(rows: AnyRow[], query: LiveQuery): AnyRow[] {
  let out = rows;
  if (query.order) {
    const { column, ascending = false } = query.order;
    out = [...rows].sort((x, y) => {
      const c = compare(x[column], y[column]);
      return ascending ? c : -c;
    });
  }
  if (query.limit && out.length > query.limit) out = out.slice(0, query.limit);
  return out;
}

function matches(row: AnyRow, query: LiveQuery): boolean {
  if (!query.eq) return true;
  const [column, value] = query.eq;
  return String(row[column]) === String(value);
}

export function useLiveTable<K extends TableName>(table: K, query: LiveQuery = {}): LiveResult<Tables[K]> {
  const eqColumn = query.eq?.[0];
  const eqValue = query.eq?.[1];
  const orderColumn = query.order?.column;
  const ascending = query.order?.ascending ?? false;
  const limit = query.limit;
  const enabled = query.enabled ?? true;
  const queryKey = JSON.stringify([table, eqColumn, eqValue, orderColumn, ascending, limit, enabled]);

  const [snapshot, setSnapshot] = useState<Snapshot>(EMPTY);

  useEffect(() => {
    if (!enabled) return;
    const sb = supabase();
    const key = PRIMARY_KEY[table] as string;
    const spec: LiveQuery = {
      eq: eqColumn !== undefined && eqValue !== undefined ? [eqColumn, eqValue] : undefined,
      order: orderColumn ? { column: orderColumn, ascending } : undefined,
      limit,
    };
    let active = true;
    const removed = new Set<string>();

    const current = (prev: Snapshot): Snapshot =>
      prev.key === queryKey ? prev : { key: queryKey, rows: [], error: null, loaded: false };

    const channel = sb
      .channel(`${table}-${++channelCounter}`)
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table,
          ...(spec.eq ? { filter: `${spec.eq[0]}=eq.${spec.eq[1]}` } : {}),
        },
        (payload: RealtimePostgresChangesPayload<AnyRow>) => {
          if (!active) return;
          if (payload.eventType === "DELETE") {
            const id = String((payload.old as AnyRow)[key]);
            removed.add(id);
            setSnapshot((prev) => {
              const base = current(prev);
              return { ...base, rows: base.rows.filter((r) => String(r[key]) !== id) };
            });
            return;
          }
          const row = payload.new as AnyRow;
          if (!matches(row, spec)) return;
          const id = String(row[key]);
          removed.delete(id);
          setSnapshot((prev) => {
            const base = current(prev);
            const rows = base.rows.filter((r) => String(r[key]) !== id);
            rows.push(row);
            return { ...base, rows: arrange(rows, spec) };
          });
        },
      )
      .subscribe();

    let request = sb.from(table).select("*");
    if (spec.eq) request = request.eq(spec.eq[0], spec.eq[1]);
    if (spec.order) request = request.order(spec.order.column, { ascending: spec.order.ascending ?? false });
    if (spec.limit) request = request.limit(spec.limit);

    request.then(({ data, error }) => {
      if (!active) return;
      setSnapshot((prev) => {
        const base = current(prev);
        if (error) return { ...base, error: error.message, loaded: true };
        const fetched = ((data ?? []) as AnyRow[]).filter((r) => !removed.has(String(r[key])));
        const seen = new Set(base.rows.map((r) => String(r[key])));
        const merged = [...base.rows, ...fetched.filter((r) => !seen.has(String(r[key])))];
        return { ...base, rows: arrange(merged, spec), error: null, loaded: true };
      });
    });

    return () => {
      active = false;
      sb.removeChannel(channel);
    };
  }, [table, eqColumn, eqValue, orderColumn, ascending, limit, enabled, queryKey]);

  const visible = snapshot.key === queryKey ? snapshot : EMPTY;
  return {
    rows: visible.rows as unknown as Tables[K][],
    loading: enabled && !visible.loaded,
    error: visible.error,
  };
}

export function useLiveRow<K extends TableName>(
  table: K,
  id: string | null | undefined,
): { row: Tables[K] | null; loading: boolean; error: string | null } {
  const key = PRIMARY_KEY[table];
  const { rows, loading, error } = useLiveTable(table, { eq: [key, id ?? ""], enabled: Boolean(id) });
  return { row: rows[0] ?? null, loading, error };
}
