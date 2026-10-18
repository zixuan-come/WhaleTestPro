// Describe only unambiguous presets; keep complex expressions as custom rules.
export function scheduleTime(expression) {
  const parts = String(expression || '').trim().split(/\s+/)
  if (parts.length !== 5) return '自定义时间规则'
  const [minute, hour, day, month, weekday] = parts
  const number = (value, low, high) => /^\d+$/.test(value) && Number(value) >= low && Number(value) <= high
  const pad = value => String(Number(value)).padStart(2, '0')
  if (month !== '*' || !number(minute, 0, 59)) return '自定义时间规则'
  if (hour === '*' && day === '*' && weekday === '*') return `每小时第 ${Number(minute)} 分钟`
  if (!number(hour, 0, 23)) return '自定义时间规则'
  const time = `${pad(hour)}:${pad(minute)}`
  if (day === '*' && weekday === '*') return `每天 ${time}`
  if (day === '*' && number(weekday, 0, 7)) return `每周${['日', '一', '二', '三', '四', '五', '六'][Number(weekday) % 7]} ${time}`
  if (weekday === '*' && number(day, 1, 31)) return `每月 ${Number(day)} 日 ${time}`
  return '自定义时间规则'
}
