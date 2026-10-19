import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import * as Vue from 'vue'
import { renderToString } from '@vue/server-renderer'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import { cloneRequest, requestConfig, requestDraft, serializeRequest } from '../src/utils/requestConfig.js'
import { pathParameterNames } from '../src/utils/pathParameters.js'
import { interfaceResources } from '../src/utils/interfaceResources.js'
import { extractRuleRows, serializeExtractRules } from '../src/utils/extractRules.js'
import { assertionRows, blankAssertion, serializeAssertions } from '../src/utils/assertionRules.js'

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
const pageSetup = build('../src/views/Interfaces.vue')

async function responseHtml(result) {
  const filename = '../src/components/CaseResponse.vue'
  const descriptor = parse(readFileSync(new URL(filename, import.meta.url), 'utf8')).descriptor
  const script = compileScript(descriptor, { id: 'case-response' })
  const component = Function('computed', script.content.replace(/^import[^\n]+\n/gm, '').replace('export default', 'return'))(Vue.computed)
  const template = compileTemplate({ source: descriptor.template.content, id: 'case-response', compilerOptions: { bindingMetadata: script.bindings } })
  assert.deepEqual(template.errors, [])
  const code = template.code.replace(/import\s*\{([^}]+)\}\s*from\s*['"]vue['"];?/g,
    (_, names) => `const {${names.replace(/\bas\b/g, ':')}} = Vue;`).replace('export function render', 'return function render')
  component.render = Function('Vue', code)(Vue)
  return renderToString(Vue.createSSRApp(component, { result }))
}

test('case execution displays actual response JSON even if its status assertion failed', async () => {
  const html = await responseHtml({ passed: false, actual_status: 201, duration_ms: 18,
    response_detail: { status_code: 201, headers: { 'Content-Type': 'application/json' }, body: { id: 42, quantity: 1 } },
    request_detail: { method: 'POST', url: 'http://fixture.invalid/orders' } })
  for (const text of ['响应体', '&quot;id&quot;: 42', '&quot;quantity&quot;: 1', '18 ms', '响应头', '实际请求', 'POST']) assert.ok(html.includes(text), text)
  const source = readFileSync(new URL('../src/views/Cases.vue', import.meta.url), 'utf8')
  assert.ok(source.includes('<CaseResponse :result="r" />'))
  assert.ok(source.includes('v-for="(r, i) in runs"'))
})

test('response rendering preserves falsy JSON, text and safely escapes HTML', async () => {
  for (const body of [false, 0, [], null, '<script>unsafe()</script>']) {
    const html = await responseHtml({ response_detail: { status_code: 200, headers: { 'content-type': 'application/json' }, body } })
    assert.ok(html.includes('class="response-body"'))
    assert.ok(!html.includes('响应体为空'))
    assert.ok(!html.includes('<script>unsafe()'))
  }
  assert.ok((await responseHtml({ response_detail: { status_code: 204, body: null, headers: {} } })).includes('响应体为空'))
  assert.ok((await responseHtml({ error: 'timeout', response_detail: null })).includes('本次执行未收到可展示的响应'))
  assert.ok((await responseHtml({ response_detail: { body: 'partial', body_truncated: true } })).includes('仅展示截取内容'))
})
const order = { id: 81, name: '查询订单', method: 'GET', url: '/orders/{id}', path_params: { id: '1' }, headers: { 'X-Project-Id': '1' }, params: { page: 2 }, body: null }
const other = { ...order, id: 82, name: '其他接口', path_params: { id: '9' } }
const helpers = { cloneRequest, requestConfig, requestDraft, serializeRequest, pathParameterNames, extractRuleRows, serializeExtractRules, assertionRows, blankAssertion, serializeAssertions }

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
    updateCase: async (id, data) => { calls.push(['update', id, data]); return {id,...data} }, deleteCase: async () => {}, runCase: async () => ({}),
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

test('case extraction rows refill old rules, reject duplicates and explicitly clear saved rules', async t => {
  const {state,calls}=cases(t)
  const legacy={id:7,name:'创建订单',interface_id:81,expected_status:201,extract_rules:{order_id:'$.id'}}
  state.openEdit(legacy)
  assert.deepEqual(state.form.extract_rules,[{name:'order_id',path:'$.id'}])
  state.form.extract_rules.push({name:'order_id',path:'$.other'})
  await state.save();assert.match(state.formErr.value,/重复/);assert.equal(calls.length,0)
  state.form.extract_rules=[{name:'order_id',path:'$.data.id'}]
  await state.save();assert.deepEqual(calls.find(call=>call[0]==='update')[2].extract_rules,{order_id:'$.data.id'})
  state.openEdit(legacy);state.form.extract_rules=[];await state.save()
  assert.equal(calls.filter(call=>call[0]==='update').at(-1)[2].extract_rules,null)
  assert.deepEqual(legacy.extract_rules,{order_id:'$.id'})
})

test('case assertion tables preserve typed expectations, block incomplete rows and can clear old assertions', async t => {
  const {state,calls}=cases(t)
  const original={id:7,name:'订单断言',interface_id:81,expected_status:200,assertions:[{type:'json_eq',path:'$.active',expected:false}]}
  state.openEdit(original)
  assert.equal(state.form.assertions[0].expectedType,'boolean')
  state.form.assertions[0].expectedType='number';state.form.assertions[0].expectedText='0'
  await state.save();assert.deepEqual(calls.find(row=>row[0]==='update')[2].assertions,[{type:'json_eq',path:'$.active',expected:0}])
  state.form.assertions[0].path='';const count=calls.length
  await state.save();assert.match(state.formErr.value,/JSONPath/);assert.equal(calls.length,count)
  state.form.assertions=[];await state.save()
  assert.equal(calls.filter(row=>row[0]==='update').at(-1)[2].assertions,null)
  assert.equal(original.assertions[0].expected,false)
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

const originalCase = { id: 301, name: '查询成功', interface_id: 81, expected_status: 200, retries: 0, request_overrides: { path_params: { id: '1' } } }

function unifiedPage(t, { allowLeave = false, caseLoad = async () => [originalCase] } = {}) {
  const prompts = []
  const state = pageSetup(t, {}, { ...Vue, pathParameterNames, onMounted() {}, onUnmounted() {}, onBeforeRouteLeave() {},
    useFeedback: () => ({ showMessage() {}, confirmAction: async message => { prompts.push(message); return allowLeave } }),
    useExecutionEnvironment: () => ({ envs: Vue.ref([]), selectedEnv: Vue.ref('36'), loadEnvironments: async () => {} }),
    listInterfaces: async () => [order, other], listCases: caseLoad,
  })
  return { state, prompts }
}

test('resource search retains the parent of a matching case and groups uncategorized interfaces last', () => {
  const interfaces = [{ ...order, category: '订单管理' }, { ...other, category: null }]
  const cases = [originalCase, { ...originalCase, id: 302, name: '订单不存在' }]
  const result = interfaceResources(interfaces, cases, '不存在')
  assert.equal(result.length, 1)
  assert.equal(result[0].name, '订单管理')
  assert.equal(result[0].items[0].id, 81)
  assert.deepEqual(result[0].items[0].cases.map(c => c.id), [302])
  assert.equal(result[0].items[0].caseCount, 2)
  assert.equal(interfaceResources(interfaces, cases)[1].name, '未分类')
  assert.equal(interfaceResources(interfaces, cases, 'GET')[0].items[0].cases.length, 2)
  assert.deepEqual(interfaceResources(interfaces, cases, 'no matching resource'), [])
})

test('unified selection loads both resource types and cancellation keeps the edited case selected', async t => {
  const { state, prompts } = unifiedPage(t)
  await state.load()
  assert.deepEqual(state.selection.value, { type: 'interface', id: 81 })
  await state.selectCase(originalCase)
  state.selectionDirty.value = true
  await state.openWorkspace(other)
  assert.equal(state.selectedCase.value.id, 301)
  assert.equal(prompts.length, 1)
  await state.openCreate()
  assert.equal(state.showModal.value, false)
  state.selectionBusy.value = true
  assert.equal(await state.canLeaveSelection(), false)
  assert.equal(prompts.length, 2)
})

test('confirmed navigation clears the dirty state, and saving selects the returned case without remounting', async t => {
  const { state } = unifiedPage(t, { allowLeave: true })
  await state.load()
  await state.selectCase(originalCase)
  state.selectionDirty.value = true
  await state.createCaseFor(other)
  assert.equal(state.selectionDirty.value, false)
  const version = state.selectionVersion.value
  const created = { ...originalCase, id: 305, interface_id: 82, name: '新用例' }
  state.caseSaved(created)
  assert.equal(state.selectionVersion.value, version)
  assert.equal(state.selectedCase.value.id, 305)
  state.caseSaved({ ...created, name: '重命名用例' })
  assert.equal(state.caseItems.value.filter(c => c.id === 305).length, 1)
  assert.equal(state.caseItems.value.find(c => c.id === 305).name, '重命名用例')
  await state.createCaseFor(other)
  assert.ok(state.selectionVersion.value > version)
})

test('a failed case list remains distinguishable while interfaces can still be inspected', async t => {
  const { state } = unifiedPage(t, { caseLoad: async () => { throw Error('用例读取失败') } })
  await state.load()
  assert.equal(state.error.value, '')
  assert.equal(state.workspaceItem.value.id, 81)
  assert.equal(state.caseError.value, '用例读取失败')
})

test('unified debug saves a request directly into the parent inline editor', async t => {
  const events = []
  const state = workspaceSetup(t, { interfaceData: order, modelValue: '36', initialTab: 'debug', unified: true }, {
    ...Vue, ...helpers, useFeedback: () => ({ showMessage() {} }), $emit: (...args) => events.push(args),
  })
  state.draft.value.pathParams.id = 'abc'
  await state.saveAsCase()
  assert.equal(events[0][0], 'create-case')
  assert.equal(events[0][1].path_params.id, 'abc')
  assert.equal(events[0][2], 200)
  assert.equal(state.tab.value, 'debug')
})

test('inline case save uses its own configuration, updates the tree and runs only saved values', async t => {
  const events = [], calls = []
  const props = Vue.reactive({ interfaceData: order, interfaceId: 81, detailMode: true, embedded: true, caseData: originalCase, envId: '36' })
  const state = caseSetup(t, props, { ...Vue, ...helpers, onMounted() {}, useRouter: () => ({}),
    useFeedback: () => ({ showMessage() {}, confirmAction: async () => false }), $emit: (...args) => events.push(args),
    useExecutionEnvironment: () => ({ envs: Vue.ref([]), selectedEnv: Vue.ref(''), loadEnvironments: async () => {} }),
    updateCase: async (id, payload) => { calls.push(['save', id, payload]); return { ...payload, id } },
    runCase: async (...args) => { calls.push(['run', ...args]); return { passed: true, actual_status: 200 } },
  })
  state.interfaces.value = [order]
  state.openEdit(originalCase)
  assert.equal(state.dirty.value, false)
  state.form.name = '新名称'
  state.requestForm.value.pathParams.id = '2'
  assert.equal(state.dirty.value, true)
  await state.onRun(originalCase)
  assert.equal(calls.length, 0)
  await state.save()
  assert.equal(calls[0][2].request_overrides.path_params.id, '2')
  assert.equal(state.dirty.value, false)
  assert.equal(state.showModal.value, true)
  assert.equal(events.find(e => e[0] === 'saved')[1].name, '新名称')
  await state.onRun(originalCase)
  assert.deepEqual(calls[1], ['run', 301, '36'])
  assert.equal(state.showResult.value, true)
})
