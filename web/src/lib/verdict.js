// One definition of "inflated / padded / holds up", shared by the course page,
// the leaderboard and the teacher page. The thresholds are copy, not statistics:
// they exist to turn a difference into a sentence, and the sentence is always
// shown next to the two numbers that produced it.

export function verdictOf(coursera, starisk) {
  if (coursera == null || starisk == null) return 'unknown';
  const inflation = coursera - starisk;
  if (inflation >= 1.5) return 'inflated';
  if (inflation >= 0.5) return 'padded';
  return 'holds-up';
}

export const VERDICT = {
  inflated: { label: 'Inflated', badge: 'badge-error', bar: 'bg-error' },
  padded: { label: 'Padded', badge: 'badge-warning', bar: 'bg-warning' },
  'holds-up': { label: 'Holds up', badge: 'badge-success', bar: 'bg-success' },
  unknown: { label: 'No rating', badge: 'badge-ghost', bar: 'bg-base-300' },
};
