import { useEffect, useRef } from 'react';
import {
  HANDOFF_BROADCAST_CHANNEL,
  HANDOFF_BROADCAST_TIMEOUT_MS,
  type HandoffBroadcastMessage,
  readPluginKeyFromUrl,
  stripPluginParamFromUrl,
} from '@/shared/utils/popupHandoffProtocol';
import { logRegressionError } from '@/shared/debug/consoleDiagnostics';
import { getRuntimeLanguageTranslations } from '@/shared/i18n';

// ---------------------------------------------------------------------------
//  Title blink utility — draws attention to an existing tab
// ---------------------------------------------------------------------------

let blinkTimer: ReturnType<typeof setInterval> | null = null;
let blinkTimeout: ReturnType<typeof setTimeout> | null = null;
let savedOriginalTitle: string | null = null;

/** Flag to prevent self-delegation: when this tab is broadcasting a
 *  plugin-launch-request, its own listener must not claim it. */
let isPluginDelegating = false;

function startTitleBlink(alertTitle: string) {
  stopTitleBlink();

  savedOriginalTitle = document.title;
  let show = true;

  blinkTimer = setInterval(() => {
    document.title = show ? alertTitle : (savedOriginalTitle ?? document.title);
    show = !show;
  }, 800);

  blinkTimeout = setTimeout(() => stopTitleBlink(), 5000);

  const onVis = () => {
    if (!document.hidden) {
      stopTitleBlink();
      document.removeEventListener('visibilitychange', onVis);
    }
  };
  document.addEventListener('visibilitychange', onVis);
}

function stopTitleBlink() {
  if (blinkTimer) {
    clearInterval(blinkTimer);
    blinkTimer = null;
  }
  if (blinkTimeout) {
    clearTimeout(blinkTimeout);
    blinkTimeout = null;
  }
  if (savedOriginalTitle !== null) {
    document.title = savedOriginalTitle;
    savedOriginalTitle = null;
  }
}

/**
 * Reads `?plugin=<key>` from the URL and calls `openTool(key)` once the app
 * is ready.  The parameter is consumed (removed from the URL) immediately so
 * that a page refresh does not re-trigger the tool.
 *
 * Uses BroadcastChannel to delegate to an existing tab when possible:
 *   - If an existing tab is open, it claims the launch and the new tab closes.
 *   - If no existing tab responds, the new tab handles the launch itself.
 */
export function usePluginLaunch(openTool: ((key: string) => void) | undefined): void {
  const openToolRef = useRef(openTool);
  openToolRef.current = openTool;

  // -----------------------------------------------------------------------
  //  BroadcastChannel: listen for plugin launch requests from new tabs.
  //  When this (existing) tab receives a plugin-launch-request, it claims it
  //  by sending plugin-launch-accepted, then calls openTool.
  // -----------------------------------------------------------------------
  useEffect(() => {
    if (typeof window === 'undefined') return;

    const channel = new BroadcastChannel(HANDOFF_BROADCAST_CHANNEL);

    channel.onmessage = (event: MessageEvent<HandoffBroadcastMessage>) => {
      const msg = event.data;
      if (msg?.type === 'plugin-launch-request' && !isPluginDelegating) {
        const currentOpenTool = openToolRef.current;
        if (!currentOpenTool) return;

        channel.postMessage({
          type: 'plugin-launch-accepted',
          toolKey: msg.toolKey,
        } satisfies HandoffBroadcastMessage);

        try {
          currentOpenTool(msg.toolKey);
        } catch (error) {
          logRegressionError('[plugin-launch] Failed to open tool:', msg.toolKey, error);
        }

        const { t } = getRuntimeLanguageTranslations();
        startTitleBlink(t.pluginLaunchedTitleBlink);
      }
    };

    return () => channel.close();
  }, []);

  // -----------------------------------------------------------------------
  //  On mount: if URL has plugin param, try delegating to an existing tab.
  //  If no tab responds, handle the launch here.
  // -----------------------------------------------------------------------
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (!openTool) return;

    const pluginKey = readPluginKeyFromUrl(window.location.href);
    if (!pluginKey) return;

    const nextUrl = stripPluginParamFromUrl(window.location.href);
    window.history.replaceState(window.history.state, '', nextUrl);

    const channel = new BroadcastChannel(HANDOFF_BROADCAST_CHANNEL);
    let settled = false;

    const cleanup = () => {
      settled = true;
      channel.close();
    };

    channel.onmessage = (event: MessageEvent<HandoffBroadcastMessage>) => {
      const msg = event.data;
      if (msg?.type === 'plugin-launch-accepted' && msg.toolKey === pluginKey && !settled) {
        cleanup();
        isPluginDelegating = false;
        try {
          window.close();
        } catch {
          /* close() may be blocked */
        }
      }
    };

    isPluginDelegating = true;
    channel.postMessage({
      type: 'plugin-launch-request',
      toolKey: pluginKey,
    } satisfies HandoffBroadcastMessage);

    setTimeout(() => {
      if (!settled) {
        cleanup();
        isPluginDelegating = false;
        try {
          openTool(pluginKey);
        } catch (error) {
          logRegressionError('[plugin-launch] Failed to open tool:', pluginKey, error);
        }
      }
    }, HANDOFF_BROADCAST_TIMEOUT_MS);
  }, [openTool]);
}
