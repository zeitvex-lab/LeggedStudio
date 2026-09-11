import { createContext, createElement, useContext, type ReactNode } from 'react';
import { useResolvedTheme } from './useTheme';

const EffectiveThemeContext = createContext<'light' | 'dark'>('light');

interface EffectiveThemeProviderProps {
  value: 'light' | 'dark';
  children: ReactNode;
}

export function EffectiveThemeProvider({ value, children }: EffectiveThemeProviderProps) {
  return createElement(EffectiveThemeContext.Provider, { value }, children);
}

export function useEffectiveTheme(): 'light' | 'dark' {
  return useContext(EffectiveThemeContext);
}

export { useResolvedTheme };
