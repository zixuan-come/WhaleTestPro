// Optional build setting supports reverse proxies, HTTPS and custom ports.
export function grafanaUrl(origin = globalThis.location?.origin || 'http://localhost', configured = import.meta.env?.VITE_GRAFANA_URL || '') {
  if (configured) {
    try {
      const url = new URL(configured, origin)
      if (['http:', 'https:'].includes(url.protocol) && !url.username && !url.password) return url.href
    } catch { /* Fall back to the current deployment host. */ }
  }
  const url = new URL(origin)
  url.port = '3000'; url.pathname = '/d/perf-dash'; url.search = ''; url.hash = ''
  return url.href
}
