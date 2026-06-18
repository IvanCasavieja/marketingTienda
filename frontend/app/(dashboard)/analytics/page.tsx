import dynamic from "next/dynamic";

// Disable SSR for the analytics page entirely — it uses useTranslation,
// dynamic date state, and streaming which all cause hydration mismatches
// when React compares server HTML against client's first render.
const AnalyticsClient = dynamic(() => import("./AnalyticsClient"), {
  ssr: false,
});

export default function Page() {
  return <AnalyticsClient />;
}
