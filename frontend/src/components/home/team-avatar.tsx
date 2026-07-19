"use client";

import { useState } from "react";
import Image from "next/image";

/** Headshot with a graceful fallback: if the photo 404s (teammate hasn't committed
 *  their image yet), show initials instead of the browser's broken-image alt text. */
export function TeamAvatar({ photo, name }: { photo: string | null; name: string }) {
  const [failed, setFailed] = useState(false);

  if (photo && !failed) {
    return (
      <Image
        src={photo}
        alt={name}
        width={112}
        height={112}
        onError={() => setFailed(true)}
        className="h-14 w-14 shrink-0 rounded-full object-cover ring-1 ring-black/[0.06]"
      />
    );
  }
  const initials = name
    .split(" ")
    .map((part) => part[0])
    .join("");
  return (
    <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-muted text-sm font-semibold tracking-wide text-subtle ring-1 ring-black/[0.06]">
      {initials}
    </span>
  );
}
