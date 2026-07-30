const SHANGHAI_FORMATTER = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23',
})

function parseBackendTime(value) {
  const raw = String(value)
  // MySQL UTC timestamps are serialized without an offset; explicit offsets must be preserved.
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw) ? raw : `${raw}Z`
  return new Date(normalized)
}

export function formatShanghaiDateTime(value) {
  if (!value) return '—'

  const date = parseBackendTime(value)
  if (Number.isNaN(date.getTime())) return '—'

  const parts = Object.fromEntries(
    SHANGHAI_FORMATTER.formatToParts(date)
      .filter(part => part.type !== 'literal')
      .map(part => [part.type, part.value]),
  )

  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second}`
}