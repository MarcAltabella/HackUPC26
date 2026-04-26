export function logHref(citation: { run_id: string; run_number: number; t: number }) {
  const params = new URLSearchParams({
    scenario: citation.run_id,
    runNumber: String(citation.run_number),
    startT: String(Math.max(0, citation.t - 3)),
    endT: String(citation.t + 3),
  });
  return `/logs?${params.toString()}`;
}
