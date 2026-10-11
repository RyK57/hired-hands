"use client";

import { createContext, useContext } from "react";
import { useLiveRow } from "@/lib/live";
import type { Cell } from "@/lib/types";

interface CellContextValue {
  cell: Cell | null;
  loading: boolean;
}

const CellContext = createContext<CellContextValue>({ cell: null, loading: true });

export function CellProvider({ children }: { children: React.ReactNode }) {
  const { row, loading } = useLiveRow("cell", "cell");
  return <CellContext.Provider value={{ cell: row, loading }}>{children}</CellContext.Provider>;
}

export function useCell(): CellContextValue {
  return useContext(CellContext);
}
