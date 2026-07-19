"use client";

import { useParams } from "next/navigation";
import { FounderDetail } from "@/components/founders/founder-detail";

export default function FounderDetailPage() {
  const { id } = useParams<{ id: string }>();
  return (
    <div className="mx-auto max-w-3xl px-8 py-8">
      {id && <FounderDetail founderId={id} />}
    </div>
  );
}
