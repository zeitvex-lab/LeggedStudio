/**
 * App State Hook
 * Provides convenient access to app-wide UI state
 */
import { useUIStore } from '@/store';
import { translations } from '@/shared/i18n';

/**
 * Hook for accessing app-wide UI state
 * Theme and language are persisted via UIStore
 */
export function useAppState() {
  const theme = useUIStore((state) => state.theme);
  const setTheme = useUIStore((state) => state.setTheme);
  const lang = useUIStore((state) => state.lang);
  const setLang = useUIStore((state) => state.setLang);
  const os = useUIStore((state) => state.os);

  // Get translations for current language
  const t = translations[lang];

  return {
    // Theme
    theme,
    setTheme,
    toggleTheme: () => setTheme(theme === 'light' ? 'dark' : 'light'),
    isDarkMode: theme === 'dark' || 
      (theme === 'system' && typeof window !== 'undefined' && 
       window.matchMedia('(prefers-color-scheme: dark)').matches),

    // Language
    lang,
    setLang,
    t,
    toggleLang: () => setLang(lang === 'en' ? 'zh' : 'en'),

    // OS
    os,
    isMac: os === 'mac',
  };
}

export default useAppState;
