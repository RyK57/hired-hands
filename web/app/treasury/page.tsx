import type { Metadata } from "next";
import { Treasury } from "@/components/treasury";

export const metadata: Metadata = { title: "Treasury" };

export default function TreasuryPage() {
  return <Treasury />;
}
