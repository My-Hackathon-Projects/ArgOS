"use client";

import { useParams } from "next/navigation";
import { Container } from "@/components/ui/container";
import { OpportunityDetail } from "@/components/opportunities/opportunity-detail";

export default function OpportunityDetailPage() {
  const { id } = useParams<{ id: string }>();
  return (
    <Container className="max-w-5xl">
      {id && <OpportunityDetail opportunityId={id} />}
    </Container>
  );
}
