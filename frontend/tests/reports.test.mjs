import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import * as Vue from 'vue'
import { parse, compileScript } from '@vue/compiler-sfc'
import { preferredReportType, rememberReportType, REPORT_TYPES } from '../src/utils/reportPreferences.js'

const descriptor = parse(readFileSync(new URL('../src/views/Reports.vue', import.meta.url), 'utf8')).descriptor
const script = compileScript(descriptor, { id: 'reports-contract' }).content
const rewrite = source => source.replace(/import\s*\{([^}]+)\}\s*from\s*['"]vue['"];?/g,
  (_, names) => `const {${names.replace(/\bas\b/g, ':')}} = Vue;`).replace(/^import .+$/gm, '')
const page = (id = 'run-1') => ({ items: [{ id, name: id, kind: 'case' }], page: 1, page_size: 20,
  total: 1, total_pages: 1, passed_count: 1, failed_count: 0, running_count: 0, pass_rate: 1 })
const deferred = () => { let resolve; return { promise: new Promise(r => resolve = r), resolve: value => resolve(value) } }

function view(t, request = async () => page(), route = { query: {} }) {
  const callbacks = []
  const auth = Vue.reactive({ username: 'report-a', currentProjectId: 1, token: 'synthetic' })
  const calls = []
  const options = Function('Vue', 'listExecutionReports', 'useAuthStore', 'formatShanghaiDateTime',
    'preferredReportType', 'rememberReportType', 'REPORT_TYPES', 'ReportExecutionDetail', 'useRoute',
    rewrite(script).replace('export default', 'return'))(
    { ...Vue, onMounted() {}, onBeforeUnmount(callback) { callbacks.push(callback) } },
    params => { calls.push(params); return request(params) }, () => auth, value => value,
    preferredReportType, rememberReportType, REPORT_TYPES, null, () => route)
  const scope = Vue.effectScope()
  const state = scope.run(() => options.setup({}, { expose() {} }))
  t.after(() => { callbacks.forEach(callback => callback()); scope.stop() })
  return { state, auth, calls, callbacks }
}

test('report preferences survive reload and remain isolated by account and project', () => {
  const values = new Map(), storage = { getItem: key => values.get(key), setItem: (key, value) => values.set(key, value) }
  rememberReportType('a', 1, 'suite', storage)
  rememberReportType('b', 1, 'regression', storage)
  assert.equal(preferredReportType('a', 1, storage), 'suite')
  assert.equal(preferredReportType('b', 1, storage), 'regression')
  assert.equal(preferredReportType('a', 2, storage), 'case')
  assert.equal(preferredReportType('', 1, storage), 'case')
  assert.equal(preferredReportType('a', 1, { getItem: () => 'broken' }), 'case')
  assert.equal(preferredReportType('a', 1, { getItem() { throw Error('disabled') } }), 'case')
  assert.doesNotThrow(() => rememberReportType('a', 1, 'case', { setItem() { throw Error('quota') } }))
})

test('switching categories cannot display a late response from another category', async t => {
  const first = deferred(), second = deferred()
  const { state } = view(t, params => params.kind === 'suite' ? second.promise : first.promise)
  const old = state.load(1)
  state.switchType('suite')
  second.resolve(page('run-suite'))
  await Vue.nextTick(); await new Promise(resolve => setImmediate(resolve))
  first.resolve(page('run-old'))
  await old
  assert.equal(state.items.value[0].id, 'run-suite')
  assert.equal(state.reportType.value, 'suite')
})

test('search, status and date filters are sent to the server before pagination', async t => {
  const { state, calls } = view(t)
  state.search.value = '  跨页名称  '; state.statusFilter.value = 'failed'
  state.dateFrom.value = '2026-10-18'; state.dateTo.value = '2026-10-19'
  await state.load(3)
  assert.deepEqual(calls[0], { kind: 'case', page: 3, page_size: 20, q: '跨页名称',
    status: 'failed', date_from: '2026-10-18', date_to: '2026-10-19' })
})

test('changing projects invalidates old requests and resets filters', async t => {
  const old = deferred()
  const { state, auth, calls } = view(t, () => calls.length === 1 ? old.promise : Promise.resolve(page('run-new-project')))
  const pending = state.load(1)
  state.search.value = 'old search'
  auth.currentProjectId = 2
  await Vue.nextTick(); await new Promise(resolve => setImmediate(resolve))
  old.resolve(page('run-old-project')); await pending
  assert.equal(state.items.value[0].id, 'run-new-project')
  assert.equal(state.search.value, '')
})

test('logout clears report data and counts without sending requests', async t => {
  const { state, auth, calls } = view(t)
  await state.load(1)
  auth.token = ''; auth.currentProjectId = null
  await Vue.nextTick()
  assert.deepEqual(state.items.value, [])
  assert.equal(state.passedTotal.value, 0)
  assert.equal(state.reportTotal.value, 0)
  assert.equal(calls.length, 1)
})

test('unmount prevents an outstanding response from restoring report rows', async t => {
  const result = deferred(), { state, callbacks } = view(t, () => result.promise)
  const pending = state.load(1)
  callbacks.forEach(callback => callback())
  result.resolve(page('run-late')); await pending
  assert.deepEqual(state.items.value, [])
})

test('a regression result link opens its exact report even outside the first page and clears on project change', async t => {
  const { state, auth } = view(t, async () => page('run-2'), { query: { kind: 'regression', report: 'run-999' } })
  state.initialize()
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(state.reportType.value, 'regression')
  assert.equal(state.linkedReportId.value, 'run-999')
  auth.currentProjectId = 2
  await Vue.nextTick()
  assert.equal(state.linkedReportId.value, null)
})
