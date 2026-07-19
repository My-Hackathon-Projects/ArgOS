import { Container } from "@/components/ui/container";
import { PageHeader } from "@/components/ui/page-header";
import { FoundersTable } from "@/components/founders/founders-table";

export default function FoundersPage() {
  return (
    <Container className="max-w-5xl">
      <PageHeader
        eyebrow="Founders"
        title="Discovered people"
        subtitle="Every person resolved from the signal feed. The Founder Score follows the person, across whatever they build next."
      />
      <div className="mt-10">
        <FoundersTable />
      </div>
    </Container>
  );
}
