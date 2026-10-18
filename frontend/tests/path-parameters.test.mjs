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
    ...Vue, onMounted() {}, onUnmounted() {}, onBeforeRouteLeave() {}, listCases: async () => [], ...api, Modal: modal,
    KeyValueEditor: { render: () => null }, EnvironmentSelect: { render: () => null },
    InterfaceResourceTree: { render: () => null }, InterfaceWorkspace: { render: () => null },
    PathParameterEditor: editor, pathParameterNames, pathParameterValues,
    CategorySelect: { render: () => null },
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
  await state.openCreate()
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

test('interface execution and case entry open the unified workspace', async t => {
  const { state, calls } = page(t)
  state.items.value = [order]
  await state.onRun(order)
  assert.equal(state.workspaceItem.value.id, 81)
  assert.equal(state.workspaceTab.value, 'debug')
  await state.openWorkspace(order, 'cases')
  assert.equal(state.workspaceTab.value, 'cases')
  assert.deepEqual(calls, [])
})

test('API adapter sends Path overrides in the body and leaves the legacy request body null', async () => {
  const calls = []
  const source = readFileSync(new URL('../src/api/interface.js', import.meta.url), 'utf8')
    .replace(/^import .+$/gm, '').replaceAll('export const ', 'const ')
  const run = Function('http', source + '\nreturn runInterface')({ post: (...args) => calls.push(args) })
  run(81, 36, { id: '2' })
  run(81, undefined)
  run(81, 36, undefined, { path_params: { id: '3' }, params: { page: '2' }, headers: null, body: null })
  assert.deepEqual(calls, [
    ['/interfaces/81/run', { path_params: { id: '2' } }, { params: { env_id: 36 } }],
    ['/interfaces/81/run', null, { params: {} }],
    ['/interfaces/81/run', { request_overrides: { path_params: { id: '3' }, params: { page: '2' }, headers: null, body: null } }, { params: { env_id: 36 } }],
  ])
})
