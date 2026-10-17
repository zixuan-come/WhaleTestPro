import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import * as Vue from 'vue'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import { renderToString } from '@vue/server-renderer'
import { pathParameterNames, pathParameterValues } from '../src/utils/pathParameters.js'

function compile(file) {
  const descriptor = parse(readFileSync(new URL(file, import.meta.url), 'utf8')).descriptor
  const script = compileScript(descriptor, { id: file })
  const template = compileTemplate({ source: descriptor.template.content, id: file, compilerOptions: { bindingMetadata: script.bindings } })
  assert.deepEqual(template.errors, [])
  const names = Object.keys(script.imports)
  const code = script.content.replace(/^import[\s\S]*?\bfrom\s*['"][^'"]+['"];?/gm, '').replace('export default', 'return')
  return mocks => {
    const component = Function(...names, code)(...names.map(name => mocks[name] ?? Vue[name]))
    const renderCode = template.code.replace(/import \{([^}]+)\} from "vue"/, (_, imports) => 'const {' + imports.replace(/\bas\b/g, ':') + '} = Vue')
    component.render = Function('Vue', renderCode.replace('export function render', 'return function render'))(Vue)
    return component
  }
}

const editor = compile('../src/components/PathParameterEditor.vue')({ pathParameterNames })
const buildPage = compile('../src/views/Interfaces.vue')
const modal = { setup(props, { slots }) { return () => Vue.h('section', [slots.default?.(), slots.foot?.()]) } }

function page(t, { run } = {}) {
  const calls = []
  const messages = []
  const envs = Vue.ref([{ id: 36, name: 'WhaleShop', base_url: 'http://orders.invalid' }])
  const selectedEnv = Vue.ref('36')
  const api = Object.fromEntries([
    'listInterfaces', 'createInterface', 'updateInterface', 'deleteInterface', 'runInterface',
    'renameCategory', 'deleteCategory', 'getInterfaceReferences', 'migrateInterfaceCases',
  ].map(name => [name, async (...args) => {
    calls.push({ name, args })
    return name === 'listInterfaces' ? [] : (name === 'runInterface' ? (run ? run(...args) : { passed: true }) : {})
  }]))
  const component = buildPage({
    ...Vue, onMounted() {}, onUnmounted() {}, ...api, Modal: modal,
    KeyValueEditor: { render: () => null }, EnvironmentSelect: { render: () => null },
    PathParameterEditor: editor, pathParameterNames, pathParameterValues,
    useFeedback: () => ({ showMessage: (...args) => messages.push(args), confirmAction: async () => false }),
    useExecutionEnvironment: () => ({ envs, selectedEnv, loadEnvironments: async () => {} }),
  })
  const scope = Vue.effectScope()
  t.after(() => scope.stop())
  const state = scope.run(() => component.setup({}, { expose() {} }))
  return { state, calls, messages, html: () => renderToString(Vue.createSSRApp({ ...component, setup: () => state })) }
}

const order = { id: 81, name: '查询单个订单', method: 'GET', url: '/orders/{id}', path_params: { id: '1' } }

test('identifies and deduplicates Path placeholders without consuming legacy variables or Query values', () => {
  assert.deepEqual(pathParameterNames('/teams/{team-id}/orders/{id}/{id}?q={q}'), ['team-id', 'id'])
  assert.deepEqual(pathParameterNames('/orders/${order_id}'), [])
  assert.deepEqual(pathParameterNames('/orders/{{order_id}}'), [])
  assert.deepEqual(pathParameterValues('/orders/{id}', { id: 0, old: 'stale' }), { id: 0 })
  assert.deepEqual(pathParameterValues('/orders/{constructor}'), { constructor: '' })
})

test('Path editor renders identified names, supports variables, and tracks URL changes', async () => {
  const props = Vue.reactive({ url: '/teams/{team}/orders/{id}', modelValue: { team: '7', id: '${order_id}' }, idPrefix: 'path', disabled: false })
  const events = []
  const state = editor.setup(props, { expose() {}, emit: (...args) => events.push(args) })
  const html = () => renderToString(Vue.createSSRApp({ ...editor, setup: () => state }, props))
  assert.match(await html(), /value="\$\{order_id\}"/)
  state.updateValue('id', '2')
  assert.deepEqual(events.at(-1), ['update:modelValue', { team: '7', id: '2' }])
  props.url = '/orders/{id}'
  assert.deepEqual(state.names.value, ['id'])
  assert.doesNotMatch(await html(), /路径参数 team/)
})

test('new interfaces automatically reveal Path parameters when entering a URL', async t => {
  const { state, html } = page(t)
  state.openCreate()
  state.form.url = '/orders/{id}'
  await Vue.nextTick()
  assert.equal(state.requestTab.value, 'path')
  assert.equal(state.pathParamCount.value, 1)
  assert.match(await html(), /aria-label="路径参数 id"/)
})

test('editing saves defaults separately from Query parameters and drops removed Path names', async t => {
  const { state, calls } = page(t)
  state.openEdit({ ...order, url: '/teams/{team}/orders/{id}', path_params: { team: '7', id: '1' }, params: { page: 2 } })
  state.form.url = '/orders/{id}'
  state.form.pathParams.id = '3'
  await state.save()
  const saved = calls.find(call => call.name === 'updateInterface')
  assert.deepEqual(saved.args[1].path_params, { id: '3' })
  assert.deepEqual(saved.args[1].params, { page: '2' })
  assert.equal(saved.args[1].url, '/orders/{id}')
})

test('execute opens inputs with defaults and sends only temporary overrides', async t => {
  const { state, calls, html } = page(t)
  await state.onRun(order)
  assert.equal(calls.length, 0)
  assert.equal(state.showRunConfig.value, true)
  assert.match(await html(), /id="run-path-param-0"[^>]*value="1"/)
  state.runPathParams.value.id = '2'
  await state.submitRun()
  assert.deepEqual(calls, [{ name: 'runInterface', args: [81, '36', { id: '2' }] }])
  assert.equal(order.path_params.id, '1')
  assert.equal(state.showRunConfig.value, false)
  assert.equal(state.showRunResult.value, true)
})

test('missing values stop the request and cancel never sends', async t => {
  const { state, calls } = page(t)
  await state.onRun({ ...order, path_params: null })
  await state.submitRun()
  assert.match(state.runError.value, /请填写路径参数：id/)
  state.runPathParams.value.id = '1'
  assert.equal(state.runError.value, '')
  state.closeRunConfig()
  assert.deepEqual(calls, [])
})

test('a failed request keeps the current draft available for retry', async t => {
  const { state } = page(t, { run: async () => { throw Error('暂时无法连接') } })
  await state.onRun(order)
  state.runPathParams.value.id = 'abc'
  await state.submitRun()
  assert.equal(state.showRunConfig.value, true)
  assert.equal(state.runPathParams.value.id, 'abc')
  assert.equal(state.runError.value, '暂时无法连接')
  assert.equal(state.runningId.value, null)
})

test('pending execution cannot be duplicated or cancelled', async t => {
  let finish
  const { state, calls } = page(t, { run: () => new Promise(resolve => { finish = resolve }) })
  await state.onRun(order)
  const pending = state.submitRun()
  await state.submitRun()
  state.closeRunConfig()
  assert.equal(calls.length, 1)
  assert.equal(state.showRunConfig.value, true)
  finish({ passed: true })
  await pending
  assert.equal(state.runningId.value, null)
})

test('fixed paths and legacy variable paths retain one-click execution', async t => {
  const { state, calls } = page(t)
  await state.onRun({ ...order, url: '/orders/1' })
  await state.onRun({ ...order, url: '/orders/${order_id}' })
  assert.equal(state.showRunConfig.value, false)
  assert.equal(calls.length, 2)
  assert.equal(calls[1].args[2], undefined)
})

test('API adapter sends Path overrides in the body and leaves the legacy request body null', async () => {
  const calls = []
  const source = readFileSync(new URL('../src/api/interface.js', import.meta.url), 'utf8')
    .replace(/^import .+$/gm, '').replaceAll('export const ', 'const ')
  const run = Function('http', source + '\nreturn runInterface')({ post: (...args) => calls.push(args) })
  run(81, 36, { id: '2' })
  run(81, undefined)
  assert.deepEqual(calls, [
    ['/interfaces/81/run', { path_params: { id: '2' } }, { params: { env_id: 36 } }],
    ['/interfaces/81/run', null, { params: {} }],
  ])
})
