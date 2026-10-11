import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

test('eight-column request header uses the same wide grid as its data rows', () => {
  const source = readFileSync(new URL('../src/views/Perf.vue', import.meta.url), 'utf8')
  const header = source.match(/class="([^"]*detail-row-head[^"]*)"/)
  assert.ok(header)
  assert.ok(header[1].split(/\s+/).includes('detail-row-wide'))
  assert.match(source, /class="detail-row detail-row-wide"/)
  const columns = source.match(/\.detail-row-wide\s*\{grid-template-columns:([^;}]*)/)
  assert.equal(columns[1].trim().split(/\s+/).length, 8)
  assert.match(source, /\.detail-row:not\(\.detail-row-wide\)/)
})
