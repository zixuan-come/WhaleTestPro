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



const typed = { status: ['paid', 'pending'], page: 2, include_deleted: false, missing: null }
const api = { id: 1, name: 'query', method: 'GET', url: '/orders', params: typed, headers: null, body: null }


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
