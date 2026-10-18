import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import * as Vue from 'vue'
import { parse, compileScript } from '@vue/compiler-sfc'
import { regressionRows } from '../src/utils/regression.js'

const descriptor = parse(readFileSync(new URL('../src/views/Regression.vue', import.meta.url), 'utf8')).descriptor
const script = compileScript(descriptor, { id: 'regression-workflow' }).content
  .replace(/import\s*\{([^}]+)\}\s*from\s*['"]vue['"];?/g, (_, names) => `const {${names.replace(/\bas\b/g, ':')}} = Vue;`)
  .replace(/^import .+$/gm, '')
const deferred = () => { let resolve; return { promise: new Promise(r => resolve = r), resolve: value => resolve(value) } }
const tick = () => new Promise(resolve => setImmediate(resolve))
const ready = key => ({ ready: true, preview_key: key, groups: [], warnings: [] })

function view(t, overrides = {}) {
  const calls = [], callbacks = [], auth = Vue.reactive({ username: 'workflow-user', token: 'synthetic', currentProjectId: 1 })
  const selectedEnv = Vue.ref('1')
  const options = Function('Vue', 'useAuthStore', 'regressionOptions', 'previewRegression', 'runSelectedRegression',
    'useExecutionEnvironment', 'EnvironmentSelect', 'regressionRows', 'getProjectNotifications', script.replace('export default', 'return'))(
    { ...Vue, onMounted() {}, onBeforeUnmount(fn) { callbacks.push(fn) } }, () => auth,
    overrides.options || (async () => ({ suites: [{ id: 1, name: '订单套件' }], cases: [
      { id: 2, name: '创建订单', tags: ['order'], interface_name: '创建' }, { id: 3, name: '查询用户', tags: ['user'], interface_name: '用户' } ] })),
    async selection => { calls.push({ type: 'preview', selection }); return overrides.preview ? overrides.preview(selection) : ready('key') },
    async selection => { calls.push({ type: 'run', selection }); return overrides.run ? overrides.run(selection) : { report_id: 'run-1', results: [] } },
    () => ({ envs: Vue.ref([]), selectedEnv, loadEnvironments: async () => [] }), null, regressionRows,
    overrides.notifications || (async () => ({enabled:true,configured:true,can_manage:true})))
  const scope = Vue.effectScope(), state = scope.run(() => options.setup({}, { expose() {} }))
  t.after(() => { callbacks.forEach(fn => fn()); scope.stop() })
  return { state, calls, auth, selectedEnv }
}

test('nothing runs until a nonempty selection has a valid current preview', async t => {
  const { state, calls } = view(t)
  await state.loadOptions(); await state.onRun()
  assert.equal(calls.length, 0)
  state.toggle(1); assert.equal(state.canRun.value, false)
  await state.loadPreview(); assert.equal(state.canRun.value, true)
  await state.onRun()
  assert.deepEqual(calls.at(-1).selection, { mode: 'suite', ids: [1], env_id: 1, preview_key: 'key', notify: false })
})

test('search and tag filters select visible cases without silently discarding checked cases', async t => {
  const { state } = view(t)
  await state.loadOptions(); state.changeMode('case')
  state.tagFilter.value = 'order'; state.selectVisible()
  assert.deepEqual(state.selectedIds.value, [2])
  state.tagFilter.value = ''; state.search.value = '用户'; state.selectVisible()
  assert.deepEqual(state.selectedIds.value, [2, 3])
  state.changeMode('suite')
  assert.deepEqual(state.selectedIds.value, [])
})

test('a late preview cannot restore an old selection or environment', async t => {
  const first = deferred(), { state, selectedEnv } = view(t, { preview: () => first.promise })
  state.toggle(1); const request = state.loadPreview()
  selectedEnv.value = '2'
  first.resolve(ready('old')); await request
  assert.equal(state.plan.value, null)
  assert.equal(state.canRun.value, false)
})

test('double clicks do not send another execution', async t => {
  const pending = deferred(), { state, calls } = view(t, { run: () => pending.promise })
  state.toggle(1); await state.loadPreview()
  const run = state.onRun(); await state.onRun()
  assert.equal(calls.filter(item => item.type === 'run').length, 1)
  pending.resolve({ results: [] }); await run
})

test('switching project clears selection and ignores an old execution result', async t => {
  const pending = deferred(), { state, auth } = view(t, { run: () => pending.promise })
  state.toggle(1); await state.loadPreview(); const run = state.onRun()
  auth.currentProjectId = 2; await tick()
  pending.resolve({ report_id: 'run-old', results: [] }); await run
  assert.equal(state.summary.value, null)
  assert.deepEqual(state.selectedIds.value, [])
  assert.equal(state.running.value, false)
})

test('changed content refreshes the preview and asks for a new explicit start', async t => {
  const { state, calls } = view(t, { run: async () => { const error = Error('changed'); error.status = 409; throw error } })
  state.toggle(1); await state.loadPreview(); await state.onRun()
  assert.match(state.runError.value, /已刷新清单/)
  assert.equal(calls.filter(item => item.type === 'run').length, 1)
  assert.equal(calls.filter(item => item.type === 'preview').length, 2)
})

test('failed scenario and dataset results show useful reasons and suite names', () => {
  const rows = regressionRows([{ type: 'suite', name: '订单套件', detail: { results: [
    { type: 'scenario', name: '下单流程', passed: false, detail: [{ passed: true }, { passed: false, expected_status: 200, actual_status: 500 }] },
    { type: 'case', name: '参数化查询', passed: false, detail: [{ passed: false, assertions: [{ passed: false }] }] },
  ] } }])
  assert.equal(rows[0].name, '下单流程')
  assert.equal(rows[0].suite_name, '订单套件')
  assert.match(rows[0].reason, /200.*500/)
  assert.match(rows[1].reason, /断言未通过/)
})

test('unconfigured or disabled notifications cannot be requested, and status failures allow testing without notification', async t => {
  const {state,calls}=view(t,{notifications:async()=>({enabled:false,configured:false,can_manage:false})})
  await state.loadOptions();await tick()
  assert.equal(state.notificationReady.value,false)
  state.toggle(1);await state.loadPreview();state.notify.value=true
  await state.onRun();assert.equal(calls.at(-1).selection.notify,false)
  assert.equal(state.notificationText.value,'本项目尚未配置飞书通知')
})

test('an old notification response cannot enable sending for another project', async t => {
  const pending=deferred(),next=deferred();let count=0
  const {state,auth}=view(t,{notifications:()=>++count===1?pending.promise:next.promise})
  const request=state.loadNotification();auth.currentProjectId=2;await tick()
  pending.resolve({enabled:true,configured:true,can_manage:true});await request;await tick()
  assert.equal(state.notify.value,false)
  assert.equal(state.notification.value,null)
  next.resolve({enabled:false,configured:false,can_manage:false});await tick()
  assert.equal(state.notificationReady.value,false)
})
