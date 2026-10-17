import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import * as Vue from 'vue'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import { cloneRequest, requestConfig, requestDraft, serializeRequest } from '../src/utils/requestConfig.js'
import { pathParameterNames } from '../src/utils/pathParameters.js'

function build(file) {
  const descriptor = parse(readFileSync(new URL(file, import.meta.url), 'utf8')).descriptor
  const script = compileScript(descriptor, { id: file })
  assert.deepEqual(compileTemplate({ source: descriptor.template.content, id: file, compilerOptions: { bindingMetadata: script.bindings } }).errors, [])
  const names = Object.keys(script.imports)
  const code = script.content.replace(/^import[\s\S]*?\bfrom\s*['"][^'"]+['"];?/gm, '').replace('export default', 'return')
  return (t, props, mocks = {}) => {
    const component = Function(...names, code)(...names.map(name => mocks[name] ?? Vue[name]))
    const scope = Vue.effectScope()
    t.after(() => scope.stop())
    return scope.run(() => component.setup(props, { expose() {}, emit: mocks.$emit || (() => {}) }))
  }
}
const workspaceSetup = build('../src/components/InterfaceWorkspace.vue')
const caseSetup = build('../src/views/Cases.vue')
const editorSetup = build('../src/components/RequestEditor.vue')
const order = { id: 81, name: '查询订单', method: 'GET', url: '/orders/{id}', path_params: { id: '1' }, headers: { 'X-Project-Id': '1' }, params: { page: 2 }, body: null }
const other = { ...order, id: 82, name: '其他接口', path_params: { id: '9' } }
const helpers = { cloneRequest, requestConfig, requestDraft, serializeRequest, pathParameterNames }

function workspace(t, run = async () => ({ response: { status_code: 200, body: { id: 1 } } })) {
  const calls = [], created = []
  const props = Vue.reactive({ interfaceData: cloneRequest(order), modelValue: '36', initialTab: 'debug', environments: [] })
  const state = workspaceSetup(t, props, { ...Vue, ...helpers, runInterface: async (...args) => { calls.push(args); return run(...args) },
    useFeedback: () => ({ showMessage() {} }), EnvironmentSelect: {}, RequestEditor: {}, Cases: {} })
  state.casesPanel.value = { openCreate: (...args) => created.push(args) }
  return { state, props, calls, created }
}

function cases(t, { embedded = true, create = async () => ({}) } = {}) {
  const calls = []
  const state = caseSetup(t, { interfaceId: embedded ? 81 : null, interfaceData: embedded ? order : null, embedded }, {
    ...Vue, ...helpers, onMounted() {}, useRouter: () => ({ push() {} }), useFeedback: () => ({ showMessage() {}, confirmAction: async () => false }),
    useExecutionEnvironment: () => ({ envs: Vue.ref([]), selectedEnv: Vue.ref('36'), loadEnvironments: async () => {} }),
    listCases: async id => { calls.push(['list', id]); return [] }, listInterfaces: async () => [order, other],
    createCase: async data => { calls.push(['create', data]); return create(data) },
    updateCase: async (id, data) => { calls.push(['update', id, data]); return {} }, deleteCase: async () => {}, runCase: async () => ({}),
    EnvironmentSelect: {}, Modal: {}, RequestEditor: {},
  })
  return { state, calls }
}

test('request drafts preserve values independently and distinguish explicit clears', () => {
  const first = requestDraft(requestConfig(order)), second = requestDraft(requestConfig(order))
  first.pathParams.id = 'abc'
  first.headers = []
  first.params = []
  const result = serializeRequest(first, order.url)
  assert.deepEqual(result, { path_params: { id: 'abc' }, headers: null, params: null, body: null })
  assert.equal(second.pathParams.id, '1')
  assert.equal(order.path_params.id, '1')
  assert.equal(requestConfig(order, { headers: null }).headers, null)
})

test('request validation rejects missing Path values, duplicate Headers and invalid JSON', () => {
  const draft = requestDraft(requestConfig(order))
  draft.pathParams.id = ''
  assert.throws(() => serializeRequest(draft, order.url), /路径参数/)
  draft.pathParams.id = '1'
  draft.headers = [{ enabled: true, key: 'Accept', value: 'a' }, { enabled: true, key: 'accept', value: 'b' }]
  assert.throws(() => serializeRequest(draft, order.url), /重复/)
  draft.headers = []
  draft.bodyType = 'json'
  draft.body = '[1]'
  assert.throws(() => serializeRequest(draft, order.url), /JSON 对象/)
  draft.body = '{invalid'
  assert.throws(() => serializeRequest(draft, order.url), /合法 JSON/)
})

test('shared request editor chooses the error tab without losing draft text', t => {
  const props = Vue.reactive({ url: order.url, modelValue: requestDraft(requestConfig(order)), idPrefix: 'test', disabled: false })
  const state = editorSetup(t, props, { ...Vue, pathParameterNames, PathParameterEditor: {}, KeyValueEditor: {} })
  assert.equal(state.tab.value, 'path')
  props.modelValue.body = '{incomplete'
  state.focusError({ tab: 'body' })
  assert.equal(state.tab.value, 'body')
  assert.equal(props.modelValue.body, '{incomplete')
})

test('workspace debug sends all four request fields as temporary values', async t => {
  const { state, calls } = workspace(t)
  state.draft.value.pathParams.id = 'abc'
  state.draft.value.headers = []
  state.draft.value.params = []
  await state.send()
  assert.deepEqual(calls[0], [81, '36', undefined, { path_params: { id: 'abc' }, headers: null, params: null, body: null }])
  assert.equal(order.path_params.id, '1')
})

test('save last request uses its original unrendered values even after the draft changes', async t => {
  const { state, created } = workspace(t)
  state.draft.value.headers = [{ key: 'Authorization', value: 'Bearer ${token}', enabled: true }]
  await state.send()
  state.draft.value.pathParams.id = 'abc'
  await state.saveAsCase(true)
  assert.equal(state.tab.value, 'cases')
  assert.equal(created[0][0].path_params.id, '1')
  assert.equal(created[0][0].headers.Authorization, 'Bearer ${token}')
  assert.equal(created[0][1], 200)
  assert.notEqual(created[0][0], state.lastRequest.value)
})

test('save current draft carries its values without sending a request', async t => {
  const { state, calls, created } = workspace(t)
  state.draft.value.pathParams.id = 'abc'
  await state.saveAsCase()
  assert.equal(calls.length, 0)
  assert.equal(created[0][0].path_params.id, 'abc')
})

test('missing Path value or environment prevents HTTP execution', async t => {
  const { state, props, calls } = workspace(t)
  state.draft.value.pathParams.id = ''
  await state.send()
  assert.match(state.error.value, /路径参数/)
  state.draft.value.pathParams.id = '1'
  props.modelValue = ''
  await state.send()
  assert.match(state.error.value, /执行环境/)
  assert.equal(calls.length, 0)
})

test('pending sends cannot duplicate and late responses cannot overwrite another interface', async t => {
  let finish
  const { state, props, calls } = workspace(t, () => new Promise(resolve => { finish = resolve }))
  const pending = state.send()
  await state.send()
  assert.equal(calls.length, 1)
  props.interfaceData = cloneRequest(other)
  await Vue.nextTick()
  finish({ response: { status_code: 200 } })
  await pending
  assert.equal(state.result.value, null)
  assert.equal(state.draft.value.pathParams.id, '9')
  assert.equal(state.running.value, false)
})

test('network failure retains debug draft for retry', async t => {
  const { state } = workspace(t, async () => { throw Error('network failed') })
  state.draft.value.pathParams.id = '2'
  await state.send()
  assert.equal(state.error.value, 'network failed')
  assert.equal(state.draft.value.pathParams.id, '2')
  assert.equal(state.running.value, false)
})

test('embedded cases load only their interface and create with a preselected association', async t => {
  const { state, calls } = cases(t)
  await state.load()
  state.openCreate({ path_params: { id: 'abc' }, headers: null, params: null, body: null }, 400)
  assert.equal(state.form.interface_id, 81)
  assert.equal(state.form.expected_status, 400)
  assert.equal(state.independentRequest.value, true)
  await state.save()
  const saved = calls.find(call => call[0] === 'create')[1]
  assert.equal(saved.interface_id, 81)
  assert.deepEqual(saved.request_overrides.path_params, { id: 'abc' })
  assert.equal(saved.expected_status, 400)
  assert.deepEqual(calls[0], ['list', 81])
})

test('editing a legacy case retains inheritance until independent values are selected', async t => {
  const { state, calls } = cases(t)
  const legacy = { id: 7, name: 'legacy', interface_id: 81, expected_status: 200 }
  state.openEdit(legacy)
  assert.equal(state.independentRequest.value, false)
  await state.save()
  assert.equal(calls.find(call => call[0] === 'update')[2].request_overrides, null)
  state.openEdit({ ...legacy, request_overrides: { path_params: { id: '3' } } })
  assert.equal(state.requestForm.value.pathParams.id, '3')
  assert.equal(state.requestForm.value.headers[0].key, 'X-Project-Id')
})

test('global case overview can still create and select another interface', async t => {
  const { state } = cases(t, { embedded: false })
  await state.load()
  state.openCreate()
  state.form.interface_id = 82
  assert.equal(state.requestForm.value.pathParams.id, '9')
  state.form.interface_id = 81
  assert.equal(state.requestForm.value.pathParams.id, '1')
})

test('failed case saves keep name, request draft and advanced settings for retry', async t => {
  const { state } = cases(t, { create: async () => { throw Error('save failed') } })
  state.openCreate()
  state.requestForm.value.pathParams.id = 'abc'
  state.form.assertions = '[{"type":"json_eq","path":"$.id","expected":1}]'
  await state.save()
  assert.equal(state.showModal.value, true)
  assert.equal(state.formErr.value, 'save failed')
  assert.equal(state.requestForm.value.pathParams.id, 'abc')
  assert.ok(state.form.assertions.includes('json_eq'))
})

test('case API filters by interface and retains the project-wide list entry', () => {
  const calls = []
  const source = readFileSync(new URL('../src/api/case.js', import.meta.url), 'utf8')
    .replace(/^import .+$/gm, '').replaceAll('export const ', 'const ')
  const list = Function('http', source + '\nreturn listCases')({ get: (...args) => calls.push(args) })
  list(81)
  list()
  assert.deepEqual(calls, [['/cases', { params: { interface_id: 81 } }], ['/cases']])
})
