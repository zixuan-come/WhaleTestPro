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

const resultDescriptor = descriptor('../src/components/SuiteRunResult.vue')
const resultScript = compileScript(resultDescriptor, { id: 'suite-result' })
const SuiteRunResult = Function('Vue', vueImports(resultScript.content).replace('export default', 'return'))(Vue)
SuiteRunResult.render = render(resultDescriptor, 'suite-result', resultScript.bindings)

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
  const feedback = []
  const auth = Vue.reactive({ username:'suite-user', currentProjectId:1, token:'synthetic' })
  const SuiteContentPicker = { props:['modelValue','disabled'], render: () => Vue.h('div', { class:'suite-picker-test' }, '按名称选择测试内容') }
  const desc = descriptor('../src/views/TestSuites.vue')
  const script = compileScript(desc, { id: 'suite-characterization' })
  const source = script.content.replace(/^import[^\n]*\n/gm, '').replace('export default', 'return')
  const options = Function(...Object.keys(api), 'Modal', 'SuiteContentPicker', 'SuiteRunResult', 'useAuthStore', 'showMessage', 'confirmAction', 'alert', 'confirm', source)(
    ...Object.values(api), Modal, SuiteContentPicker, SuiteRunResult, () => auth, (message,type) => { alerts.push(message);feedback.push({message,type}) }, async () => true, () => { throw Error('Unexpected native alert') }, () => { throw Error('Unexpected native confirm') })
  options.render = render(desc, 'suite-characterization', script.bindings)
  const state = options.data()
  for (const [name, method] of Object.entries(options.methods)) state[name] = method.bind(state)
  for (const [name, getter] of Object.entries(options.computed)) Object.defineProperty(state, name, { get: () => getter.call(state) })
  return { options, state, calls, alerts, auth, feedback }
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
  for (const width of [960, 400, 600]) assert.match(html, new RegExp(`max-width:${width}px`))
  for (const text of ['新建套件', '运行套件', '运行结果', 'synthetic-env', 'synthetic-suite']) assert.ok(html.includes(text))
  assert.match(html, /<form/)
  assert.match(html, /maxlength="100"/)
  assert.ok(!html.includes('套件类型'))
  assert.ok(!html.includes('type="radio"'))
  assert.ok(!html.includes('场景 ID') && !html.includes('用例 ID'))
  assert.ok(html.includes('hide-scrollbar'))
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
        editingId: 8, form: { name: 'unfinished', description: 'draft' },
        selection: { scenario_ids:[1,2], case_ids:[3], tags:['smoke'] },
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
    assert.deepEqual(view.form, { name: '', description: '' })
    assert.deepEqual(view.selection, { scenario_ids:[], case_ids:[], tags:[] })
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

test('create preserves chosen order and dynamic tags, and resets only after success', async () => {
  const { state, calls, feedback } = suite()
  state.showCreateDialog = true
  state.form = { name: '  smoke  ', description: '  description  ' }
  state.pickerReady = true
  state.selection = { scenario_ids:[1,2], case_ids:[3], tags:['smoke','p0'] }
  await state.submitForm()
  assert.deepEqual(calls, [['create', { name: 'smoke', description: 'description', type: 'mixed',
    scenario_ids: [1, 2], case_ids: [3], tags: ['smoke', 'p0'] }]])
  assert.equal(state.showCreateDialog, false)
  assert.deepEqual(state.form, { name: '', description: '' })
  assert.deepEqual(feedback,[{message:'套件创建成功',type:'success'}])
})

test('edit uses the selected ID and preserves omitted selections as null', async () => {
  const { state, calls } = suite()
  state.editSuite({ id: 8, name: 'existing', type: 'case', case_ids: [3] })
  state.pickerReady = true
  assert.equal(state.showEditDialog, true)
  await state.submitForm()
  assert.deepEqual(calls, [['update', 8, { name: 'existing', description: null,
    scenario_ids: null, case_ids: [3], tags: null }]])
  assert.equal(state.editingId, null)
})

test('save failure leaves dialog state and user input intact', async () => {
  const { state, alerts } = suite({ createSuite: async () => { throw Error('synthetic failure') } })
  state.showCreateDialog = true
  state.form.name = 'preserved'
  state.pickerReady = true
  await state.submitForm()
  assert.equal(state.showCreateDialog, true)
  assert.equal(state.form.name, 'preserved')
  assert.match(state.saveError, /synthetic failure/)
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

test('pending suite saves reject duplicate submits and cannot close the editor', async () => {
  let finish, requests=0
  const {state}=suite({createSuite:()=>{requests++;return new Promise(resolve=>finish=resolve)}})
  state.showCreateDialog=true;state.pickerReady=true;state.form.name='pending'
  const pending=state.submitForm();state.closeDialog();await state.submitForm()
  assert.equal(requests,1);assert.equal(state.showCreateDialog,true)
  finish();await pending;assert.equal(state.showCreateDialog,false)
})

test('a late save cannot close a new-project draft or replace its selection', async () => {
  let finish
  const {state,options,auth}=suite({createSuite:()=>new Promise(resolve=>finish=resolve)})
  state.showCreateDialog=true;state.pickerReady=true;state.form.name='old'
  const pending=state.submitForm();auth.currentProjectId=2;options.watch.projectIdentity.call(state)
  state.openCreate();state.form.name='new';state.selection.case_ids=[9]
  finish();await pending
  assert.equal(state.showCreateDialog,true);assert.equal(state.form.name,'new');assert.deepEqual(state.selection.case_ids,[9])
})

test('suite search and pagination include suites after the first API page', async () => {
  const fixtures=Array.from({length:205},(_,index)=>({id:index+1,name:index===204?'目标套件':'suite '+index,description:'smoke'}))
  const requests=[]
  const {state}=suite({listSuites:async params=>{requests.push(params);return fixtures.slice(params.skip,params.skip+params.limit)}})
  await state.fetchSuites()
  assert.deepEqual(requests,[{skip:0,limit:100},{skip:100,limit:100},{skip:200,limit:100}])
  assert.equal(state.suites.length,205);assert.equal(state.pageCount,11)
  state.page=11;assert.equal(state.pageSuites.length,5)
  state.search='目标';state.page=1
  assert.deepEqual(state.filteredSuites.map(item=>item.id),[205])
  state.search='SMOKE';assert.equal(state.filteredSuites.length,205)
})

test('late suite listing and execution cannot show old project data', async () => {
  const listings=[];let finishRun
  const {state,auth,options}=suite({listSuites:()=>new Promise(resolve=>listings.push(resolve)),apiRunSuite:()=>new Promise(resolve=>finishRun=resolve)})
  const listing=state.fetchSuites();state.runSuite(8)
  const running=state.executeRun()
  auth.currentProjectId=2;options.watch.projectIdentity.call(state)
  finishRun({suite_name:'old suite',total:1,passed:1,failed:0})
  await running;assert.equal(state.runResult,null);assert.equal(state.running,false)
  listings[0]([{id:1,name:'old suite'}]);await listing
  assert.equal(state.suites.length,0)
  assert.equal(state.loadingSuites,true)
  listings[1]([]);await new Promise(resolve=>setImmediate(resolve))
  assert.equal(state.loadingSuites,false)
})

test('suite execution rejects duplicate clicks while the request is pending', async () => {
  let finish,count=0
  const {state}=suite({apiRunSuite:()=>{count++;return new Promise(resolve=>finish=resolve)}})
  state.runSuite(8);const pending=state.executeRun();await state.executeRun();state.runSuite(9)
  assert.equal(count,1);assert.equal(state.runningSuiteId,8)
  finish({suite_name:'original',total:1,passed:1,failed:0});await pending
  assert.equal(state.running,false);assert.equal(state.runResult.suite_name,'original')
})

test('suite results preserve execution order and open failures, including data rows and missing resources', async () => {
  const result={suite_name:'订单套件',duration_ms:1240,total:3,passed:1,failed:2,pass_rate:33.33,results:[
    {type:'scenario',name:'登录流程',passed:true,detail:[{case_name:'用户登录',passed:true,expected_status:200,actual_status:200}]},
    {type:'case',name:'订单数据组',passed:false,detail:[{passed:true,expected_status:200,actual_status:200},{passed:false,expected_status:200,actual_status:500,assertions:[{passed:false,type:'status'}]}]},
    {type:'case',id:99,name:null,passed:false,error:'用例不存在'},
  ]}
  const html=await renderToString(Vue.createSSRApp(SuiteRunResult,{result}))
  assert.ok(html.includes('1.24 秒')&&html.includes('33.33%')&&html.includes('3 项'))
  assert.ok(html.indexOf('登录流程')<html.indexOf('订单数据组'))
  assert.match(html,/<details class="suite-execution-item">/)
  assert.equal((html.match(/class="suite-execution-item" open/g)||[]).length,2)
  for(const text of ['数据组 2','期望状态码 200，实际 500','用例 #99','用例不存在'])assert.ok(html.includes(text),text)
  const empty=await renderToString(Vue.createSSRApp(SuiteRunResult,{result:{total:0,passed:0,failed:0,pass_rate:0}}))
  assert.ok(empty.includes('无执行项')&&!empty.includes('全部通过'))
})
