import type { Metadata } from "next";
import { ArmDetail } from "@/components/arm-detail";
import { ARM_ROLES } from "@/lib/types";

export const metadata: Metadata = { title: "Arm" };

export function generateStaticParams() {
  return ARM_ROLES.map((role) => ({ role }));
}

export default async function ArmPage({ params }: { params: Promise<{ role: string }> }) {
  const { role } = await params;
  return <ArmDetail role={role} />;
}
