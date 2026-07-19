import { redirect } from "next/navigation";

// Market research lives inside the opportunity detail now; keep the old URL working.
export default function ResearchPage() {
  redirect("/opportunities");
}
