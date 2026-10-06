import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import * as Vue from 'vue'
import { renderToString } from '@vue/server-renderer'

// Compile the actual SFCs. API doubles keep these checks completely offline.
function descriptor(relative) {
  const filename = new URL(relative, import.meta.url).pathname
  const result = parse(readFileSync(new URL(relative, import.meta.url), 'utf8'), { filename })
  assert.deepEqual(result.errors, [])
  return result.descriptor
}

function vueImports(code) {
  return code.replace(/import\s*\{([^}]+)\}\s*from\s*['"]vue['"];?/g, (_match, names) =>
    `const {${names.replace(/\bas\b/g, ':')}} = Vue;`)
}

function render(descriptor, id, bindings) {
  const result = compileTemplate({
    source: descriptor.template.content, filename: descriptor.filename, id,
    compilerOptions: { bindingMetadata: bindings },
  })
  assert.deepEqual(result.errors, [])
  return Function('Vue', vueImports(result.code).replace('export function render', 'return function render'))(Vue)
}

const modalDescriptor = descriptor('../src/components/Modal.vue')
const modalScript = compileScript(modalDescriptor, { id: 'modal-characterization' })
const Modal = Function('Vue', vueImports(modalScript.content).replace('export default', 'return'))(Vue)
Modal.render = render(modalDescriptor, 'modal-characterization', modalScript.bindings)

test('CI executes suite modal regressions before the frontend build', () => {
  const workflow = readFileSync(new URL('../../.github/workflows/ci.yml', import.meta.url), 'utf8')
  const frontendJob = workflow.split(/^  frontend:\s*$/m)[1]
  assert.ok(frontendJob, 'frontend CI job must exist')
  const commands = [...frontendJob.matchAll(/^\s+- run:\s+(.+)$/gm)].map(match => match[1].trim())
  const regressionStep = commands.indexOf('npm run test:refactor')
  assert.ok(regressionStep >= 0, 'suite modal regression script must run in CI')
  assert.ok(regressionStep < commands.indexOf('npm run build'))
  const { scripts } = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'))
  assert.match(scripts['test:refactor'], /\bsuite-modal\.test\.mjs\b/)
})

function suite(overrides = {}) {
  const calls = []
  const api = {
    listSuites: async () => [], listEnvironments: async () => [],
    createSuite: async payload => calls.push(['create', payload]),
    updateSuite: async (id, payload) => calls.push(['update', id, payload]),
    apiDeleteSuite: async id => calls.push(['delete', id]),
    apiRunSuite: async (id, environment) => ({ suite_name: 'synthetic', total: 2, passed: 1,
      failed: 1, pass_rate: 50, duration_ms: 20, id, environment }),
    ...overrides,
  }
  const alerts = []
  const desc = descriptor('../src/views/TestSuites.vue')
  const script = compileScript(desc, { id: 'suite-characterization' })
  const source = script.content.replace(/^import[^\n]*\n/gm, '').replace('export default', 'return')
  const options = Function(...Object.keys(api), 'Modal', 'alert', 'confirm', source)(
    ...Object.values(api), Modal, message => alerts.push(message), () => true)
  options.render = render(desc, 'suite-characterization', script.bindings)
  const state = options.data()
  for (const [name, method] of Object.entries(options.methods)) state[name] = method.bind(state)
  return { options, state, calls, alerts }
}

test('all three suite dialogs render through the actual shared Modal and preserve widths/content', async () => {
  const { options } = suite()
  const component = { ...options, data: () => ({ ...options.data(),
    showCreateDialog: true, showRunDialog: true,
    environments: [{ id: 7, name: 'synthetic-env' }],
    runResult: { suite_name: 'synthetic-suite', duration_ms: 20, total: 2, passed: 1, failed: 1, pass_rate: 50 },
  }) }
  const context = {}
  await renderToString(Vue.createSSRApp(component), context)
  const html = context.teleports.body
  assert.equal((html.match(/class="modal"/g) || []).length, 3)
  for (const width of [560, 400, 600]) assert.match(html, new RegExp(`max-width:${width}px`))
  for (const text of ['新建套件', '运行套件', '运行结果', 'synthetic-env', 'synthetic-suite']) assert.ok(html.includes(text))
  assert.match(html, /<form/)
  assert.match(html, /maxlength="100"/)
})

test('closed dialogs render no teleported overlay', async () => {
  const { options } = suite()
  const context = {}
  await renderToString(Vue.createSSRApp(options), context)
  assert.equal(context.teleports?.body, undefined)
})

test('suite Modal close bindings reset create/edit state and close run/result dialogs', async () => {
  for (const mode of ['create', 'edit']) {
    const { options, calls } = suite()
    let view, tree
    const component = {
      ...options,
      data: () => ({ ...options.data(),
        showCreateDialog: mode === 'create', showEditDialog: mode === 'edit',
        editingId: 8, form: { name: 'unfinished', description: 'draft', type: 'case' },
        scenarioIdsText: '1,2', caseIdsText: '3', tagsText: 'smoke',
        showRunDialog: true, selectedEnvId: 7,
        runResult: { suite_name: 'synthetic', duration_ms: 20, total: 2, passed: 1, failed: 1, pass_rate: 50 },
      }),
      render(...args) {
        view = this
        tree = options.render.apply(this, args)
        return tree
      },
    }
    await renderToString(Vue.createSSRApp(component))
    const modals = []
    function visit(node) {
      if (Array.isArray(node)) return node.forEach(visit)
      if (!Vue.isVNode(node)) return
      if (node.type === Modal) modals.push(node)
      if (Array.isArray(node.children)) node.children.forEach(visit)
    }
    visit(tree)
    assert.equal(modals.length, 3)
    function close(title) {
      const modal = modals.find(node => node.props.title === title)
      assert.equal(typeof modal?.props.onClose, 'function', `${title} must bind the shared close event`)
      modal.props.onClose()
    }
    close(mode === 'create' ? '新建套件' : '编辑套件')
    assert.equal(view.showCreateDialog, false)
    assert.equal(view.showEditDialog, false)
    assert.equal(view.editingId, null)
    assert.deepEqual(view.form, { name: '', description: '', type: 'mixed' })
    assert.deepEqual([view.scenarioIdsText, view.caseIdsText, view.tagsText], ['', '', ''])
    assert.equal(view.showRunDialog, true)
    assert.ok(view.runResult)
    close('运行套件')
    assert.equal(view.showRunDialog, false)
    assert.equal(view.selectedEnvId, 7)
    assert.ok(view.runResult)
    close('运行结果')
    assert.equal(view.runResult, null)
    assert.deepEqual(calls, [])
  }
})

test('create preserves payload parsing and resets the form only after success', async () => {
  const { state, calls } = suite()
  state.showCreateDialog = true
  state.form = { name: '  smoke  ', description: '  description  ', type: 'mixed' }
  state.scenarioIdsText = '1, bad, 2'
  state.caseIdsText = '3'
  state.tagsText = ' smoke, ,p0 '
  await state.submitForm()
  assert.deepEqual(calls, [['create', { name: 'smoke', description: 'description', type: 'mixed',
    scenario_ids: [1, 2], case_ids: [3], tags: ['smoke', 'p0'] }]])
  assert.equal(state.showCreateDialog, false)
  assert.deepEqual(state.form, { name: '', description: '', type: 'mixed' })
})

test('edit uses the selected ID and preserves omitted selections as null', async () => {
  const { state, calls } = suite()
  state.editSuite({ id: 8, name: 'existing', type: 'case', case_ids: [3] })
  assert.equal(state.showEditDialog, true)
  await state.submitForm()
  assert.deepEqual(calls, [['update', 8, { name: 'existing', description: null, type: 'case',
    scenario_ids: null, case_ids: [3], tags: null }]])
  assert.equal(state.editingId, null)
})

test('save failure leaves dialog state and user input intact', async () => {
  const { state, alerts } = suite({ createSuite: async () => { throw Error('synthetic failure') } })
  state.showCreateDialog = true
  state.form.name = 'preserved'
  await state.submitForm()
  assert.equal(state.showCreateDialog, true)
  assert.equal(state.form.name, 'preserved')
  assert.ok(alerts.some(message => message.includes('synthetic failure')))
})

test('run retains suite/environment IDs and opens the matching result', async () => {
  const { state } = suite()
  state.runSuite(8)
  assert.equal(state.selectedEnvId, null)
  state.selectedEnvId = 7
  await state.executeRun()
  assert.equal(state.showRunDialog, false)
  assert.equal(state.runResult.id, 8)
  assert.equal(state.runResult.environment, 7)
})

test('run failure keeps the environment dialog available for retry', async () => {
  const { state, alerts } = suite({ apiRunSuite: async () => { throw Error('synthetic failure') } })
  state.runSuite(8)
  await state.executeRun()
  assert.equal(state.showRunDialog, true)
  assert.equal(state.runResult, null)
  assert.ok(alerts.some(message => message.includes('synthetic failure')))
})

test('shared close handler still emits close and respects the existing busy contract', () => {
  const events = []
  const props = { busy: false }
  const state = Modal.setup(props, { expose() {}, emit: name => events.push(name) })
  state.onClose()
  props.busy = true
  state.onClose()
  assert.deepEqual(events, ['close'])
})
