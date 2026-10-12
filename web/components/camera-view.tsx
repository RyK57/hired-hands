"use client";

import { Video } from "lucide-react";
import { useEffect, useState } from "react";
import { useCell } from "./cell-provider";
import { Empty } from "./empty";
import { cameraUrl } from "@/lib/api";

export function CameraView() {
  const { cell } = useCell();
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const url = cameraUrl(cell);
  useEffect(() => {
    if (!url || !cell?.online) {
      setSrc(null);
      return;
    }
    setFailed(false);
    setSrc(`${url}?t=${Date.now()}`);
  }, [url, cell?.online]);
  if (!src || failed) {
    return <Empty icon={Video} title="No camera feed." detail="The head camera streams here while the cell is online." compact />;
  }
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={src} alt="head camera" onError={() => setFailed(true)} className="block aspect-[4/3] w-full bg-black object-contain" />;
}
