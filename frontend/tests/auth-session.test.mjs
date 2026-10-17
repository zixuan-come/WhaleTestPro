import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createPinia, defineStore } from 'pinia'
import * as Vue from 'vue'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import { renderToString } from '@vue/server-renderer'

const oldSelection = {
  wtp_token: 'fixture-token',
  wtp_user: 'previous-user',
  wtp_tid: '73',
  wtp_tname: 'auto_project_delete_fixture团队',
  wtp_trole: 'owner',
  wtp_pid: '90',
  wtp_pname: 'previous-project',
}

function session({ teams = [], projects = [], listTeams } = {}) {
  const data = new Map(Object.entries(oldSelection))
  const storage = {
    getItem: key => data.get(key) ?? null,
    setItem: (key, value) => data.set(key, String(value)),
    removeItem: key => data.delete(key),
  }
  const calls = []
  const source = readFileSync(new URL('../src/stores/auth.js', import.meta.url), 'utf8')
    .replace(/^import .+$/gm, '')
    .replace('export const useAuthStore', 'const useAuthStore')
  const useStore = Function('defineStore', 'ref', 'listProjects', 'listTeams', 'localStorage',
    source + '\nreturn useAuthStore;')(
    defineStore, Vue.ref,
    async params => { calls.push(params); return projects },
    listTeams || (async () => teams), storage)
  return { auth: useStore(createPinia()), storage, calls }
}

function guard(auth) {
  let beforeEach
  const source = readFileSync(new URL('../src/router/index.js', import.meta.url), 'utf8')
    .replace(/^import .+$/gm, '')
    .replace('export default router', 'return router')
  Function('createRouter', 'createWebHashHistory', 'useAuthStore', 'AppLayout', source)(
    () => ({ beforeEach: fn => { beforeEach = fn } }), () => null, () => auth, {})
  return beforeEach
}

test('logout removes persisted team identity and project selection', () => {
  const { auth, storage } = session()
  auth.logout()
  assert.equal(auth.currentTeamId, null)
  assert.equal(auth.currentTeamName, '')
  assert.equal(auth.currentTeamRole, '')
  assert.equal(auth.currentProjectId, null)
  for (const key of Object.keys(oldSelection)) assert.equal(storage.getItem(key), null, key)
})

test('a new authenticated session cannot inherit the previous account selection', () => {
  const { auth, storage } = session()
  auth.setAuth('new-session-token', 'new-user')
  assert.equal(auth.currentTeamId, null)
  assert.equal(auth.currentProjectId, null)
  assert.equal(storage.getItem('wtp_tname'), null)
  assert.equal(auth.token, 'new-session-token')
})

test('entering project management validates an empty team list before rendering cached labels', async () => {
  const { auth, storage, calls } = session()
  const result = await guard(auth)({ name: 'projects', meta: { noProjectRequired: true } })
  assert.equal(result, undefined)
  assert.equal(auth.currentTeamId, null)
  assert.equal(auth.currentTeamName, '')
  assert.equal(storage.getItem('wtp_tname'), null)
  assert.equal(auth.teamStatus, 'ready')
  assert.deepEqual(calls, [])
})

test('a remembered authorized team and project survive refresh after validation', async () => {
  const { auth, calls } = session({
    teams: [{ id: 73, name: 'renamed-team', role: 'member' }],
    projects: [{ id: 90, name: 'renamed-project' }],
  })
  await guard(auth)({ name: 'projects', meta: { noProjectRequired: true } })
  assert.equal(auth.currentTeamName, 'renamed-team')
  assert.equal(auth.currentTeamRole, 'member')
  assert.equal(auth.currentProjectId, 90)
  assert.equal(auth.currentProjectName, 'renamed-project')
  assert.deepEqual(calls, [{ team_id: 73 }])
})

test('an inaccessible cached team switches to an authorized team and discards its old project', async () => {
  const { auth, calls } = session({
    teams: [{ id: 81, name: 'available-team', role: 'member' }],
    projects: [{ id: 91, name: 'available-project' }],
  })
  await guard(auth)({ name: 'interfaces', meta: {} })
  assert.equal(auth.currentTeamId, 81)
  assert.equal(auth.currentProjectId, 91)
  assert.deepEqual(calls, [{ team_id: 81 }])
})

test('team loading failure clears stale context and remains distinguishable from an empty list', async () => {
  const { auth, calls } = session({ listTeams: async () => { throw new Error('offline') } })
  await guard(auth)({ name: 'projects', meta: { noProjectRequired: true } })
  assert.equal(auth.currentTeamId, null)
  assert.equal(auth.currentProjectId, null)
  assert.equal(auth.teamStatus, 'error')
  assert.deepEqual(calls, [])
})

test('a team response arriving after logout cannot restore the previous team', async () => {
  let finish
  const { auth } = session({ listTeams: () => new Promise(resolve => { finish = resolve }) })
  const pending = auth.initTeam()
  auth.logout()
  finish([{ id: 73, name: 'previous-team', role: 'owner' }])
  await pending
  assert.equal(auth.token, '')
  assert.equal(auth.currentTeamId, null)
  assert.equal(auth.currentTeamName, '')
  assert.equal(auth.teamStatus, 'idle')
})

test('empty team context redirects business navigation to project management', async () => {
  const { auth } = session()
  const result = await guard(auth)({ name: 'interfaces', meta: {} })
  assert.deepEqual(result, { name: 'projects' })
  assert.equal(auth.currentTeamId, null)
})

const layoutDescriptor = parse(
  readFileSync(new URL('../src/layouts/AppLayout.vue', import.meta.url), 'utf8')).descriptor
const layoutCode = compileScript(layoutDescriptor, { id: 'auth-context-layout', inlineTemplate: true }).content
  .replace(/import\s*\{([^}]+)\}\s*from\s*['"]vue['"];?/g, (_match, names) =>
    'const {' + names.replace(/\bas\b/g, ':') + '} = Vue;')
  .replace(/^import .+$/gm, '')
  .replace('export default', 'return')

async function header(auth) {
  const component = Function('Vue', 'useRoute', 'useRouter', 'useThemeStore', 'useAuthStore',
    'listProjects', 'createProject', 'listTeams', 'createTeam', 'Modal', layoutCode)(
    Vue, () => ({ meta: { title: '项目管理' } }), () => ({}),
    () => ({ theme: 'light' }), () => auth,
    async () => [], async () => ({}), async () => [], async () => ({}), {})
  const app = Vue.createSSRApp(component)
  app.component('router-link', { setup: (_props, { slots }) => () => Vue.h('a', slots.default?.()) })
  app.component('router-view', { setup: () => () => null })
  return renderToString(app)
}

test('the actual header renders confirmed empty teams and load failures as different states', async () => {
  const { auth } = session()
  await auth.initTeam()
  const emptyHtml = await header(auth)
  assert.ok(emptyHtml.includes('暂无团队'))
  assert.ok(!emptyHtml.includes(oldSelection.wtp_tname))
  const failed = session({ listTeams: async () => { throw new Error('offline') } }).auth
  await assert.rejects(failed.initTeam())
  const failedHtml = await header(failed)
  assert.ok(failedHtml.includes('团队加载失败'))
  assert.ok(!failedHtml.includes('暂无团队'))
})

test('pending invitations show complete team names before the invitee joins a team', async () => {
  const descriptor = parse(
    readFileSync(new URL('../src/views/Teams.vue', import.meta.url), 'utf8')).descriptor
  const script = compileScript(descriptor, { id: 'team-invitation-name' })
  const code = script.content
    .replace(/import\s*\{([^}]+)\}\s*from\s*['"]vue['"];?/g, (_match, names) =>
      'const {' + names.replace(/\bas\b/g, ':') + '} = Vue;')
    .replace(/^import .+$/gm, '')
    .replace('export default', 'return')
  const apiNames = [
    'listTeams', 'listTeamMembers', 'searchTeamMemberCandidates', 'updateTeamMemberRole',
    'removeTeamMember', 'updateTeam', 'transferTeamOwnership', 'leaveTeam', 'deleteTeam',
    'inviteTeamMember', 'listTeamInvitations', 'respondTeamInvitation',
    'listTeamPermissions', 'setTeamPermission',
  ]
  const component = Function('Vue', 'useAuthStore', 'useFeedback', ...apiNames, code)(
    Vue, () => ({ currentTeamId: null, currentTeamRole: '' }),
    () => ({ showMessage() {}, confirmAction: async () => false }),
    ...apiNames.map(() => async () => []))
  const template = compileTemplate({
    source: descriptor.template.content, id: 'team-invitation-name',
    compilerOptions: { bindingMetadata: script.bindings },
  })
  assert.deepEqual(template.errors, [])
  component.render = Function('Vue', template.code
    .replace(/import\s*\{([^}]+)\}\s*from\s*['"]vue['"];?/g, (_match, names) =>
      'const {' + names.replace(/\bas\b/g, ':') + '} = Vue;')
    .replace('export function render', 'return function render'))(Vue)
  const longName = 'WhaleShop团队' + 'A'.repeat(89)
  const setup = component.setup
  component.setup = (props, context) => {
    const state = setup(props, context)
    state.invitations.value = [
      { id: 1, team_id: 102, team_name: 'WhaleShop', role: 'member' },
      { id: 2, team_id: 103, team_name: longName, role: 'admin' },
    ]
    state.invitationTotal.value = 2
    return state
  }
  const html = await renderToString(Vue.createSSRApp(component))
  assert.ok(html.includes('WhaleShop'))
  assert.ok(html.includes(longName))
  assert.ok(!html.includes('团队 #102'))
  assert.equal((html.match(/>接受<\/button>/g) || []).length, 2)
  assert.equal((html.match(/>拒绝<\/button>/g) || []).length, 2)
})
