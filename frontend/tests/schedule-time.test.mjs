import test from 'node:test'
import assert from 'node:assert/strict'
import { scheduleTime } from '../src/utils/scheduleTime.js'

test('daily and hourly presets describe execution times without changing the expressions', () => {
  assert.equal(scheduleTime('0 2 * * *'), '每天 02:00')
  assert.equal(scheduleTime(' 05   09 * * * '), '每天 09:05')
  assert.equal(scheduleTime('15 * * * *'), '每小时第 15 分钟')
})
test('weekly presets accept both Sunday aliases and monthly presets retain the day', () => {
  assert.equal(scheduleTime('30 8 * * 1'), '每周一 08:30')
  assert.equal(scheduleTime('0 0 * * 0'), '每周日 00:00')
  assert.equal(scheduleTime('0 0 * * 7'), '每周日 00:00')
  assert.equal(scheduleTime('0 2 31 * *'), '每月 31 日 02:00')
})
test('complex calendar rules keep their custom designation rather than guessing a daily time', () => {
  for (const expression of ['*/5 * * * *', '0 2 * * 1-5', '0 2 1 * 1', '0 2 * 6 *', '0,30 2 * * *']) {
    assert.equal(scheduleTime(expression), '自定义时间规则')
  }
})
test('malformed or out-of-range expressions are never described as valid preset times', () => {
  for (const expression of ['', null, '0 2 * *', '0 2 * * * *', '60 2 * * *', '0 24 * * *', '0 2 0 * *', '0 2 * * 8']) {
    assert.equal(scheduleTime(expression), '自定义时间规则')
  }
})
