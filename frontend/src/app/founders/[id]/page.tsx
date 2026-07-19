"use client";

import { useParams } from "next/navigation";
import { Container } from "@/components/ui/container";
import { FounderDetail } from "@/components/founders/founder-detail";

export default function FounderDetailPage() {
  const { id } = useParams<{ id: string }>();
  return (
    <Container className="max-w-3xl">
      {id && <FounderDetail founderId={id} />}
    </Container>
  );
}
