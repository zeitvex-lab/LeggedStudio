import React from 'react';
import { getRuntimeLanguageTranslations } from '@/shared/i18n';

interface AppErrorBoundaryProps {
  children: React.ReactNode;
}

interface AppErrorBoundaryState {
  hasError: boolean;
  error: unknown;
}

function formatErrorBoundaryMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message || error.name;
  }
  if (typeof error === 'string') {
    return error;
  }

  try {
    return JSON.stringify(error) ?? String(error);
  } catch {
    return String(error);
  }
}

export class AppErrorBoundary extends React.Component<
  AppErrorBoundaryProps,
  AppErrorBoundaryState
> {
  state: AppErrorBoundaryState = { hasError: false, error: null };

  static getDerivedStateFromError(error: unknown): AppErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: unknown, info: React.ErrorInfo): void {
    const { t } = getRuntimeLanguageTranslations();
    console.error(t.appErrorBoundaryLogPrefix, error, info.componentStack);
  }

  private handleReload = (): void => {
    window.location.reload();
  };

  private handleDismiss = (): void => {
    this.setState({ hasError: false, error: null });
  };

  render(): React.ReactNode {
    const { error, hasError } = this.state;
    if (!hasError) {
      return this.props.children;
    }

    const { lang, t } = getRuntimeLanguageTranslations();

    return (
      <div
        lang={lang === 'zh' ? 'zh-CN' : 'en'}
        role="alert"
        style={{
          position: 'fixed',
          inset: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexDirection: 'column',
          gap: 16,
          padding: 24,
          background: '#0b0d10',
          color: '#e6e8eb',
          fontFamily: 'system-ui, sans-serif',
          textAlign: 'center',
        }}
      >
        <h1 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>{t.appErrorBoundaryTitle}</h1>
        <p style={{ margin: 0, opacity: 0.7, maxWidth: 480 }}>
          {t.appErrorBoundaryMessage}
        </p>
        <pre
          style={{
            margin: 0,
            maxWidth: '90vw',
            maxHeight: '40vh',
            overflow: 'auto',
            padding: 12,
            background: '#15181c',
            borderRadius: 8,
            fontSize: 12,
            textAlign: 'left',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
        >
          {formatErrorBoundaryMessage(error)}
        </pre>
        <div style={{ display: 'flex', gap: 12 }}>
          <button
            type="button"
            onClick={this.handleReload}
            style={{
              padding: '8px 16px',
              border: 'none',
              borderRadius: 6,
              background: '#3b82f6',
              color: '#fff',
              cursor: 'pointer',
              fontSize: 14,
            }}
          >
            {t.appErrorBoundaryReload}
          </button>
          <button
            type="button"
            onClick={this.handleDismiss}
            style={{
              padding: '8px 16px',
              border: '1px solid #2a2f36',
              borderRadius: 6,
              background: 'transparent',
              color: '#e6e8eb',
              cursor: 'pointer',
              fontSize: 14,
            }}
          >
            {t.appErrorBoundaryDismiss}
          </button>
        </div>
      </div>
    );
  }
}
