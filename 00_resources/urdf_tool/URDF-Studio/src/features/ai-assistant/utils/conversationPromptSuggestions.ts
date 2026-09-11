import { translations, type Language } from '@/shared/i18n'

interface BuildConversationPromptSuggestionsOptions {
  lang: Language
  isReportFollowup: boolean
  selectedEntityName?: string | null
  focusedIssueTitle?: string | null
}

export const buildConversationPromptSuggestions = ({
  lang,
  isReportFollowup,
  selectedEntityName,
  focusedIssueTitle,
}: BuildConversationPromptSuggestionsOptions): string[] => {
  const t = translations[lang]

  if (isReportFollowup) {
    if (focusedIssueTitle) {
      return [
        t.conversationSuggestionReportFocusedIssueReason.replace('{title}', focusedIssueTitle),
        t.conversationSuggestionReportFocusedIssueFix.replace('{title}', focusedIssueTitle),
        t.conversationSuggestionReportRetest,
      ]
    }

    return [
      t.conversationSuggestionReportPrioritize,
      selectedEntityName
        ? t.conversationSuggestionReportSelectedEntity.replace('{name}', selectedEntityName)
        : t.conversationSuggestionReportSelectedEntityFallback,
      t.conversationSuggestionReportRetest,
    ]
  }

  return [
    t.conversationSuggestionGeneralRisks,
    selectedEntityName
      ? t.conversationSuggestionGeneralSelectedEntity.replace('{name}', selectedEntityName)
      : t.conversationSuggestionGeneralSelectedEntityFallback,
    t.conversationSuggestionGeneralSimulation,
  ]
}
