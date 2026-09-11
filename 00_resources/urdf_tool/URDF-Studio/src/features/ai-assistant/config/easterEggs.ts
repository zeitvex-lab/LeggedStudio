import type { AIResponse } from '../types'
import { logRegressionError } from '@/shared/debug/consoleDiagnostics'

/**
 * Helper to decode Base64 UTF-8 strings using TextDecoder
 */
export const b64DecodeUnicode = (str: string): string => {
  try {
    const binaryString = atob(str)
    const bytes = new Uint8Array(binaryString.length)
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i)
    }
    return new TextDecoder().decode(bytes)
  } catch (error) {
    logRegressionError('Failed to decode base64 string', error)
    return ''
  }
}

// Encoded Easter Eggs (Key -> Value)
export const EGGS: Record<string, string> = {
  '6L6+5aaZ56eR5oqA': '5Y+R5p2l6LS655S1',
  '54G16Laz5pe25Luj': '56Wd5L2g5oiQ5Yqf',
  '5Zug5YWL5pav5pm66IO9': '56Wd6ICB5p2/5aW95biF77yB',
  '6auY5pOO5py655S1': '5oiR54ix5bCP5rS+77yB',
  '5Zyw55Oc5py65LmZ5Lq6': '5Y+R5p2l54Oo5Zyw55Oc'
}

export const getEasterEggResponse = (prompt: string): AIResponse | null => {
  const trimPrompt = prompt.trim()
  for (const [key, val] of Object.entries(EGGS)) {
    const decodedKey = b64DecodeUnicode(key)
    if (trimPrompt === decodedKey) {
      return {
        explanation: b64DecodeUnicode(val),
        actionType: 'advice'
      }
    }
  }

  return null
}
