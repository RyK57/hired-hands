import type { Metadata } from "next";
import { Hire } from "@/components/hire";

export const metadata: Metadata = { title: "Hire" };

export default function HirePage() {
  return <Hire />;
}
