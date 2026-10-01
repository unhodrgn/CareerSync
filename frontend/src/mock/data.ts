// Demo data for screens whose backend is not built yet (recommendation).
// Replace each export with an API call when the matching endpoint lands.

/** Stable demo match percentage for a real job until the recommendation API exists. */
export function demoMatch(jobId: number): number {
  return 70 + ((jobId * 37) % 26);
}
