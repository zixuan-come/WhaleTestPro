import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import axios from 'axios'
import * as Vue from 'vue'
import { parse, compileScript } from '@vue/compiler-sfc'
import * as request from '../src/utils/requestConfig.js'
import * as extraction from '../src/utils/extractRules.js'
import * as assertion from '../src/utils/assertionRules.js'
import * as paths from '../src/utils/pathParameters.js'
import { grafanaUrl } from '../src/utils/serviceUrls.js'
import { caseToStep, equivalentCaseIds } from '../src/utils/scenarioSteps.js'
import { selectedSuiteContent, suiteCatalog } from '../src/utils/suiteSelection.js'

const read = name => readFileSync(new URL('../' + name, import.meta.url), 'utf8')
const tick = () => new Promise(resolve => setImmediate(resolve))
const deferred = () => { let resolve, reject; return { promise: new Promise((yes, no) => { resolve = yes; reject = no }), resolve, reject } }
const feedback = () => ({ showMessage() {}, confirmAction: async () => true })
const previousDocument = globalThis.document
const previousWindow = globalThis.window
before(() => {
  globalThis.document = { removeEventListener() {} }
  globalThis.window = { removeEventListener() {} }
})
after(() => {
  if (previousDocument === undefined) delete globalThis.document
  else globalThis.document = previousDocument
  if (previousWindow === undefined) delete globalThis.window
  else globalThis.window = previousWindow
})
function setup(t, name, props = {}, mocks = {}) {
  const d = parse(read('src/' + name)).descriptor, script = compileScript(d, { id: name })
  const code = script.content.replace(/^import[\s\S]*?\bfrom\s*['"][^'"]+['"];?/gm, '').replace('export default', 'return')
  const callbacks = [], all = { ...Vue, ...request, ...extraction, ...assertion, ...paths,
    onMounted() {}, onBeforeUnmount(fn) { callbacks.push(fn) }, onUnmounted(fn) { callbacks.push(fn) }, ...mocks }
  const names = Object.keys(script.imports), component = Function(...names, code)(...names.map(name => all[name]))
  const scope = Vue.effectScope()
  t.after(() => { callbacks.forEach(fn => fn()); scope.stop() })
  return scope.run(() => component.setup(props, { expose() {}, emit: mocks.emit || (() => {}) }))
}
function httpClient() {
  const auth = { token: 'token-A', username: 'alice', currentProjectId: 1, logout() { this.token = ''; this.username = '' } }
  const location = { hash: '#/interfaces' }
  const code = read('src/api/http.js').replace(/^import[^\n]+\n/gm, '').replace('export default http', 'return http')
  return { auth, location, http: Function('axios', 'useAuthStore', 'location', code)(axios, () => auth, location) }
}

test('late 401 from an old credential cannot log out the new account, but current 401 does', async () => {
  const { auth, http, location } = httpClient(), old = deferred()
  http.defaults.adapter = config => old.promise.then(() => { throw new axios.AxiosError('expired', 'ERR_BAD_REQUEST', config, null,
    { status: 401, data: {}, config }) })
  const first = http.get('/reports').catch(error => error.status)
  await tick(); auth.token = 'token-B'; auth.username = 'bob'; old.resolve(); assert.equal(await first, 401)
  assert.equal(auth.token, 'token-B'); assert.equal(location.hash, '#/interfaces')
  await assert.rejects(http.get('/reports'), error => error.status === 401)
  assert.equal(auth.token, ''); assert.equal(location.hash, '#/login')
})

test('synchronous run adapters allow long chains and proxy waits longer than the client', async () => {
  const { http } = httpClient(), calls = []
  http.defaults.adapter = async config => { calls.push(config); return { status: 200, data: {}, headers: {}, config } }
  for (const [file, name] of [['case', 'runCase'], ['case', 'runChain'], ['scenario', 'runScenario'], ['scenario', 'debugScenarioStep'], ['suite', 'runSuite'], ['interface', 'runInterface']]) {
    const code = read(`src/api/${file}.js`).replace(/^import[^\n]+\n/gm, '').replaceAll('export const ', 'const ')
    await Function('http', code + `\nreturn ${name}`)(http)(1, 1, {})
  }
  assert.ok(calls.every(config => config.timeout === 600000))
  await http.get('/cases'); assert.equal(calls.at(-1).timeout, 15000)
  const nginx = read('nginx.conf')
  assert.match(nginx, /proxy_read_timeout 660s;/)
  assert.match(nginx, /cases\/\(\[0-9\]\+\/run\|chain\)/)
})

test('uncertain execution failures direct users to reports or target data without inviting retries', async () => {
  const { http } = httpClient()
  http.defaults.adapter = async config => { throw new axios.AxiosError('timeout', 'ECONNABORTED', config) }
  await assert.rejects(http.post('/cases/1/run'), error => error.executionUncertain && /测试报告/.test(error.message))
  await assert.rejects(http.post('/interfaces/1/run'), error => error.executionUncertain && /目标数据/.test(error.message))
  await assert.rejects(http.get('/cases'), error => !error.executionUncertain && error.message === 'timeout')
  http.defaults.adapter = async config => { throw new axios.AxiosError('rejected', 'ERR_BAD_REQUEST', config, null,
    { status: 409, data: { message: '内容已变更' }, config }) }
  await assert.rejects(http.post('/cases/1/run'), error => !error.executionUncertain && error.message === '内容已变更')
  http.defaults.adapter = async config => { throw new axios.AxiosError('gateway', 'ERR_BAD_RESPONSE', config, null,
    { status: 502, data: '<html>Bad gateway</html>', config }) }
  await assert.rejects(http.post('/suites/1/run'), error => error.executionUncertain && /避免重复执行/.test(error.message))
})

const typed = { status: ['paid', 'pending'], page: 2, include_deleted: false, missing: null }
const api = { id: 1, name: 'query', method: 'GET', url: '/orders', params: typed, headers: null, body: null }
test('debug request serialization preserves unchanged JSON Query values, while edited values become text', () => {
  const draft = request.requestDraft(api)
  assert.deepEqual(request.serializeRequest(draft, '/orders').params, typed)
  draft.params.find(row => row.key === 'status').value = 'paid'
  const result = request.serializeRequest(draft, '/orders')
  assert.equal(result.params.status, 'paid'); assert.equal(result.params.page, 2)
  result.params.status = ['new']; assert.deepEqual(api.params.status, ['paid', 'pending'])
})

test('renaming an interface or independent case cannot change imported Query types', async t => {
  let interfacePayload, casePayload
  const common = { useFeedback: feedback, useExecutionEnvironment: () => ({ envs: Vue.ref([]), selectedEnv: Vue.ref(''), loadEnvironments: async () => [] }),
    onBeforeRouteLeave() {}, listInterfaces: async () => [api], listCases: async () => [],
    updateInterface: async (id, payload) => { interfacePayload = payload; return { id, ...payload } } }
  const interfaces = setup(t, 'views/Interfaces.vue', {}, common)
  interfaces.openEdit(api); interfaces.form.name = 'renamed'; await interfaces.save()
  assert.deepEqual(interfacePayload.params, typed)
  interfaces.form.params.find(row => row.key === 'page').value = '3'; await interfaces.save()
  assert.equal(interfacePayload.params.page, '3'); assert.deepEqual(interfacePayload.params.status, typed.status)
  const cases = setup(t, 'views/Cases.vue', { interfaceId: 1, interfaceData: api, embedded: true }, {
    ...common, useRouter: () => ({}), updateCase: async (id, payload) => { casePayload = payload; return { id, ...payload } } })
  cases.openEdit({ id: 7, name: 'case', interface_id: 1, expected_status: 200, request_overrides: { params: typed } })
  cases.form.name = 'renamed'; await cases.save()
  assert.deepEqual(casePayload.request_overrides.params, typed)
})

function teamsPage(t, overrides = {}) {
  const auth = Vue.reactive({ username: 'alice', token: 'synthetic', currentTeamId: 1, currentTeamRole: 'owner',
    setTeam(id, name, role) { this.currentTeamId = id; this.currentTeamRole = role }, setProject() {} })
  const state = setup(t, 'views/Teams.vue', {}, { useAuthStore: () => auth, useFeedback: feedback,
    listTeamMembers: async id => [{ id, user_id: id, role: 'member', user: { username: 'member-' + id } }],
    listTeamPermissions: async id => [{ role: 'member', permission: 'interface.write', enabled: id === 1 }], ...overrides })
  state.teams.value = [{ id: 1, name: 'A', role: 'owner' }, { id: 2, name: 'B', role: 'owner' }]
  return { state, auth }
}
test('late team details never replace current members and permissions, including A to B to A', async t => {
  const first = deferred(); let calls = 0
  const { state } = teamsPage(t, { listTeamMembers: async id => ++calls === 1 ? first.promise : [{ id, role: 'member', user: { username: 'current-' + id } }] })
  const pending = state.switchTeam(state.teams.value[0]); await state.switchTeam(state.teams.value[1])
  assert.equal(state.members.value[0].user.username, 'current-2'); assert.equal(state.permissions.value['interface.write'], false)
  await state.switchTeam(state.teams.value[0]); first.resolve([{ id: 99, user: { username: 'stale' } }]); await pending
  assert.equal(state.members.value[0].user.username, 'current-1'); assert.equal(state.permissions.value['interface.write'], true)
})
test('late member search and failed permission write cannot pollute another team', async t => {
  const search = deferred(), write = deferred()
  const { state } = teamsPage(t, { searchTeamMemberCandidates: () => search.promise, setTeamPermission: () => write.promise })
  await state.switchTeam(state.teams.value[0]); state.keyword.value = 'old'; const pendingSearch = state.search()
  const pendingWrite = state.togglePermission({ key: 'interface.write', label: '接口' }, { target: { checked: false } })
  await state.switchTeam(state.teams.value[1]); search.resolve([{ id: 99, username: 'old candidate' }]); write.reject(Error('old failure'))
  await Promise.all([pendingSearch, pendingWrite]); assert.deepEqual(state.candidates.value, [])
  assert.equal(state.permissions.value['interface.write'], false); assert.equal(state.permissionSaving.value, '')
})

test('team permission writes wait for authoritative reads, then remain saved on the same team', async t => {
  const read = deferred(); let stored = false, writes = 0
  const { state } = teamsPage(t, {
    listTeamPermissions: () => read.promise,
    setTeamPermission: async (_id, value) => { writes++; stored = value.enabled },
  })
  const pending = state.switchTeam(state.teams.value[1])
  assert.equal(state.detailsLoading.value, true); assert.equal(state.detailsReady.value, false)
  const option = { key: 'interface.write', label: '接口' }, event = { target: { checked: true } }
  await state.togglePermission(option, event); assert.equal(writes, 0)
  read.resolve([{ role: 'member', permission: option.key, enabled: false }]); await pending
  assert.equal(state.detailsReady.value, true); assert.equal(state.detailsLoading.value, false)
  await state.togglePermission(option, event)
  assert.equal(writes, 1); assert.equal(stored, true); assert.equal(state.permissions.value[option.key], true)
})

test('a successful permission write fences a same-team read that started while the write was pending', async t => {
  const write = deferred(), staleRead = deferred(); let reads = 0, stored = false
  const { state } = teamsPage(t, {
    listTeamPermissions: async () => ++reads === 2 ? staleRead.promise : [{ role: 'member', permission: 'interface.write', enabled: stored }],
    setTeamPermission: async (_id, value) => { await write.promise; stored = value.enabled },
  })
  await state.switchTeam(state.teams.value[1])
  const saving = state.togglePermission({ key: 'interface.write', label: '接口' }, { target: { checked: true } })
  const refresh = state.switchTeam(state.teams.value[1])
  write.resolve(); await saving
  assert.equal(reads, 3); assert.equal(state.permissions.value['interface.write'], true)
  staleRead.resolve([{ role: 'member', permission: 'interface.write', enabled: false }]); await refresh
  assert.equal(state.permissions.value['interface.write'], true); assert.equal(state.detailsReady.value, true)
})

test('same-team A to B to A late details cannot release a newer loading guard, and failed loads block writes', async t => {
  const oldA = deferred(), newA = deferred(); let reads = 0, writes = 0
  const { state } = teamsPage(t, {
    listTeamPermissions: async id => { reads++; return reads === 1 ? oldA.promise : reads === 3 ? newA.promise : [] },
    setTeamPermission: async () => writes++,
  })
  const first = state.switchTeam(state.teams.value[0]); await state.switchTeam(state.teams.value[1])
  const last = state.switchTeam(state.teams.value[0]); oldA.resolve([]); await first
  assert.equal(state.detailsLoading.value, true); assert.equal(state.detailsReady.value, false)
  await state.togglePermission({ key: 'case.write' }, { target: { checked: true } }); assert.equal(writes, 0)
  newA.reject(Error('failed permission GET')); await last
  assert.equal(state.detailsLoading.value, false); assert.equal(state.detailsReady.value, false)
  assert.match(state.detailsError.value, /failed permission GET/)
  await state.togglePermission({ key: 'case.write' }, { target: { checked: true } }); assert.equal(writes, 0)
})

test('case, scenario and interface handlers refuse missing or stale environment IDs', async t => {
  const rows = Vue.ref([{ id: 7, name: 'available' }]), selected = Vue.ref(''), sent = [], messages = []
  const common = { useFeedback: () => ({ showMessage: message => messages.push(message), confirmAction: async () => true }),
    useExecutionEnvironment: () => ({ envs: rows, selectedEnv: selected, loadEnvironments: async () => rows.value }),
    useRouter: () => ({}), useAuthStore: () => Vue.reactive({ token: 'synthetic', currentProjectId: 1 }),
    runCase: async (...args) => { sent.push(['case', ...args]); return [] },
    runScenario: async (...args) => { sent.push(['scenario', ...args]); return [] },
    runInterface: async (...args) => { sent.push(['interface', ...args]); return {} } }
  const cases = setup(t, 'views/Cases.vue', {}, common)
  const scenario = setup(t, 'views/Orchestration.vue', {}, common)
  scenario.currentId.value = 1; scenario.chain.value = [{ step_id: 'one' }]
  const props = Vue.reactive({ interfaceData: api, environments: rows.value, modelValue: '', initialTab: 'debug' })
  const workspace = setup(t, 'components/InterfaceWorkspace.vue', props, common)
  for (const value of ['', 'deleted']) {
    selected.value = value; props.modelValue = value
    await cases.onRun({ id: 1 }); await scenario.onRun(); await workspace.send()
    assert.equal(sent.length, 0)
    assert.equal(cases.hasExecutionEnvironment.value, false); assert.equal(scenario.hasExecutionEnvironment.value, false)
    assert.equal(workspace.hasExecutionEnvironment.value, false)
    assert.match(workspace.error.value, /请选择有效/)
  }
  rows.value = []; props.environments = []
  await cases.onRun({ id: 1 }); await scenario.onRun(); await workspace.send()
  assert.match(messages.at(-1), /环境管理/); assert.match(workspace.error.value, /环境管理/)
  rows.value = [{ id: 7, name: 'available' }]; selected.value = '7'; props.environments = rows.value; props.modelValue = '7'
  await cases.onRun({ id: 1 }); await scenario.onRun(); await workspace.send()
  assert.deepEqual(sent.map(row => row[0]), ['case', 'scenario', 'interface'])
  assert.ok(sent.every(row => String(row[2]) === '7'))
})

test('formal scene edits retain large legacy extraction sets while debug validates its own bounds', async t => {
  const sent = [], applied = [], step = { step_id: 'test', source_case_id: 1, interface_id: 1, name: 'old', method: 'GET', url: '/orders', expected_status: 200,
    extract_rules: Object.fromEntries(Array.from({ length: 101 }, (_, index) => ['v' + index, '$.id'])) }
  const state = setup(t, 'components/ScenarioStepEditor.vue', { step, envId: 1 }, { debugScenarioStep: async (...args) => sent.push(args), emit: (name, value) => applied.push([name, value]) })
  state.name.value = 'renamed'; state.apply()
  assert.equal(Object.keys(applied[0][1].extract_rules).length, 101)
  await state.send(); assert.equal(sent.length, 0); assert.match(state.debugError.value, /100/)
  state.extracts.value = [{ name: 'v'.repeat(65), path: '$.id' }]
  assert.ok(state.buildStep()); await state.send(); assert.equal(sent.length, 0); assert.match(state.debugError.value, /64/)
})

test('suite picker does not treat chain steps with SQL, datasets or retries as full independent executions', () => {
  const base = { id: 1, name: 'case', interface_id: 1, expected_status: 200 }
  for (const extra of [{ datasets: [{ user: 'a' }] }, { setup_sql: ['SELECT 1'] }, { teardown_sql: ['SELECT 1'] }, { retries: 1 }]) {
    const full = { ...base, ...extra }, step = caseToStep(full, api)
    assert.equal(equivalentCaseIds([step], [full], [api]).size, 0)
    const catalog = suiteCatalog([{ id: 1, name: 'scenario', steps: [step] }], [full], [api])
    assert.equal(selectedSuiteContent(catalog, { scenario_ids: [1], case_ids: [1] }).cases[0].included, false)
  }
  assert.deepEqual([...equivalentCaseIds([caseToStep(base, api)], [base], [api])], [1])
})

test('Grafana uses deployment hostname and allows an explicit HTTPS or same-origin dashboard URL', () => {
  assert.equal(grafanaUrl('http://cloud.example:8080'), 'http://cloud.example:3000/d/perf-dash')
  assert.equal(grafanaUrl('https://app.example', 'https://monitor.example/grafana/d/perf-dash'), 'https://monitor.example/grafana/d/perf-dash')
  assert.equal(grafanaUrl('https://app.example', '/grafana/d/perf-dash'), 'https://app.example/grafana/d/perf-dash')
  assert.equal(grafanaUrl('http://cloud.example', 'javascript:alert(1)'), 'http://cloud.example:3000/d/perf-dash')
  assert.match(read('Dockerfile'), /ARG VITE_GRAFANA_URL/)
})
test('Mock advertised URLs use the configured frontend API proxy and environment syntax matches the engine', t => {
  const mocks = setup(t, 'views/Mocks.vue', {}, { useAuthStore: () => ({ currentProjectId: 7 }), useFeedback: feedback })
  assert.equal(mocks.hitUrlPrefix.value + '/orders', '/api/mock/7/orders')
  assert.match(read('nginx.conf'), /location \/api\//)
  const envs = setup(t, 'views/Environments.vue', {}, { useFeedback: feedback })
  assert.equal(envs.refSyntax, '${key}')
})
