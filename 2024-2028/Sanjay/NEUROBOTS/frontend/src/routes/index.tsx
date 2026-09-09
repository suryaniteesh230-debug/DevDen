import { createFileRoute } from "@tanstack/react-router";
import StaffAuthGate from "@/components/StaffAuthGate";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "NextCare — Clinical Decision-Support Console" },
      {
        name: "description",
        content:
          "Edge-first multi-agent cardiac risk, prototype emergency triage, clinical reasoning, explainability, and operational priority console.",
      },
      { property: "og:title", content: "NextCare Clinical Console" },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: StaffAuthGate,
});
