import { Loading } from "@/components/empty";

export default function JobLoading() {
  return (
    <div className="card">
      <Loading rows={5} />
    </div>
  );
}
