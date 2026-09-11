/**
 * Score display helpers for inspection report UI
 */

export function getScoreColor(score: number, maxScoreForItem: number = 10): string {
  const normalizedScore = (score / maxScoreForItem) * 10
  if (normalizedScore >= 9) return 'text-emerald-600 dark:text-emerald-400'
  if (normalizedScore >= 6) return 'text-amber-600 dark:text-amber-400'
  return 'text-rose-600 dark:text-rose-400'
}

export function getScoreBgColor(score: number, maxScoreForItem: number = 10): string {
  const normalizedScore = (score / maxScoreForItem) * 10
  if (normalizedScore >= 9) return 'bg-emerald-400'
  if (normalizedScore >= 6) return 'bg-amber-400'
  return 'bg-rose-400'
}
