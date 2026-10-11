import Link from "next/link";
import { Empty } from "@/components/empty";

export default function NotFound() {
  return (
    <div className="card">
      <Empty title="There is nothing at this address." />
      <div className="border-t border-line px-4 py-3">
        <Link href="/" className="link text-sm">
          Back to the overview
        </Link>
      </div>
    </div>
  );
}
