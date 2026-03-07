// Google Analytics 4 helper
// Provides type-safe event tracking throughout the app

declare global {
  interface Window {
    gtag: (...args: unknown[]) => void
    dataLayer: unknown[]
  }
}

const GA_ID = 'G-K714WDYE3B'

export function trackEvent(
  action: string,
  params?: Record<string, string | number | boolean>,
) {
  if (typeof window.gtag === 'function') {
    window.gtag('event', action, params)
  }
}

export function trackPageView(path: string, title?: string) {
  if (typeof window.gtag === 'function') {
    window.gtag('config', GA_ID, {
      page_path: path,
      page_title: title,
    })
  }
}

export default { trackEvent, trackPageView }
