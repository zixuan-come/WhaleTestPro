export function pathParameterNames(url = '') {
  const path = url.split(/[?#]/, 1)[0]
  return [...new Set([...path.matchAll(/(?<![$\{])\{([\w-]+)\}(?!\})/g)].map(match => match[1]))]
}

export function pathParameterValues(url, values = {}) {
  return Object.fromEntries(pathParameterNames(url).map(name => [
    name, Object.hasOwn(values || {}, name) ? values[name] ?? '' : '',
  ]))
}
