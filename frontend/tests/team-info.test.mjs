import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import * as Vue from 'vue'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import { renderToString } from '@vue/server-renderer'

const descriptor = parse(readFileSync(new URL('../src/views/Teams.vue', import.meta.url), 'utf8')).descriptor
const script = compileScript(descriptor, { id: 'team-info-regression' })
const template = compileTemplate({
  source: descriptor.template.content, id: 'team-info-regression',
  compilerOptions: { bindingMetadata: script.bindings },
})
assert.deepEqual(template.errors, [])
const rewrite = source => source
  .replace(/import\s*\{([^}]+)\}\s*from\s*['"]vue['"];?/g, (_match, names) =>
    'const {' + names.replace(/\bas\b/g, ':') + '} = Vue;')
  .replace(/^import .+$/gm, '')
const apiNames = [
  'listTeams', 'listTeamMembers', 'searchTeamMemberCandidates', 'updateTeamMemberRole',
  'removeTeamMember', 'updateTeam', 'transferTeamOwnership', 'leaveTeam', 'deleteTeam',
  'inviteTeamMember', 'listTeamInvitations', 'respondTeamInvitation',
  'listTeamPermissions', 'setTeamPermission',
]

function teamPage(t, { role = 'owner', updateTeam } = {}) {
  const teams = [
    { id: 1, name: 'WhaleShop', description: '第一行\n第二行', role },
    { id: 2, name: 'Other team', description: 'Other description', role },
  ]
  const calls = []
  const messages = []
  const auth = Vue.reactive({
    currentTeamId: 1, currentTeamRole: role,
    setTeam(id, name, nextRole) { this.currentTeamId = id; this.currentTeamName = name; this.currentTeamRole = nextRole },
    setProject() {},
  })
  const api = Object.fromEntries(apiNames.map(name => [name, async () => []]))
  api.updateTeam = async (id, data) => {
    calls.push({ id, data })
    return updateTeam ? updateTeam(id, data) : { id, ...data }
  }
  const component = Function('Vue', 'useAuthStore', 'useFeedback', ...apiNames,
    rewrite(script.content).replace('export default', 'return'))(
    { ...Vue, onMounted() {} }, () => auth,
    () => ({ showMessage: (...args) => messages.push(args), confirmAction: async () => false }),
    ...apiNames.map(name => api[name]))
  component.render = Function('Vue', rewrite(template.code)
    .replace('export function render', 'return function render'))(Vue)
  const scope = Vue.effectScope()
  t.after(() => scope.stop())
  const state = scope.run(() => component.setup({}, { expose() {} }))
  state.teams.value = teams
  const html = () => renderToString(Vue.createSSRApp({ ...component, setup: () => state }))
  return { state, auth, calls, messages, html }
}

for (const role of ['owner', 'admin', 'member']) {
  test(`${role} sees team information as text by default with role-appropriate edit controls`, async t => {
    const { state, html } = teamPage(t, { role })
    const rendered = await html()
    assert.equal(state.editingTeamInfo.value, false)
    assert.ok(rendered.includes('WhaleShop'))
    assert.ok(rendered.includes('第一行\n第二行'))
    assert.ok(!rendered.includes('<textarea'))
    assert.ok(!rendered.includes('id="team-name"'))
    assert.equal(rendered.includes('>编辑</button>'), role !== 'member')
  })
}

test('cancel discards draft changes without making a request, and reopening uses saved values', async t => {
  const { state, calls, html } = teamPage(t)
  state.startTeamEdit()
  assert.ok((await html()).includes('<textarea'))
  state.editName.value = 'Unsaved name'
  state.editDescription.value = 'Unsaved description'
  state.cancelTeamEdit()
  assert.equal(state.editingTeamInfo.value, false)
  assert.equal(state.currentTeam.value.name, 'WhaleShop')
  assert.deepEqual(calls, [])
  state.startTeamEdit()
  assert.equal(state.editName.value, 'WhaleShop')
  assert.equal(state.editDescription.value, '第一行\n第二行')
})

test('an admin saves the actual draft and returns to read-only text with the server values', async t => {
  const { state, calls, auth, html } = teamPage(t, { role: 'admin' })
  state.startTeamEdit()
  state.editName.value = ' Updated team '
  state.editDescription.value = ' New first line\nNew second line '
  await state.saveTeamInfo()
  assert.deepEqual(calls, [{ id: 1, data: { name: 'Updated team', description: 'New first line\nNew second line' } }])
  assert.equal(state.editingTeamInfo.value, false)
  assert.equal(state.savingTeamInfo.value, false)
  assert.equal(auth.currentTeamName, 'Updated team')
  const rendered = await html()
  assert.ok(rendered.includes('New first line\nNew second line'))
  assert.ok(!rendered.includes('<textarea'))
})

test('a rejected save preserves the editor and draft for retry', async t => {
  const { state, messages } = teamPage(t, { updateTeam: async () => { throw Error('Save unavailable') } })
  state.startTeamEdit()
  state.editDescription.value = 'Retain this draft'
  await state.saveTeamInfo()
  assert.equal(state.editingTeamInfo.value, true)
  assert.equal(state.editDescription.value, 'Retain this draft')
  assert.equal(state.currentTeam.value.description, '第一行\n第二行')
  assert.equal(state.savingTeamInfo.value, false)
  assert.deepEqual(messages.at(-1), ['Save unavailable', 'error'])
})

test('pending saves cannot be submitted twice or cancelled before completion', async t => {
  let finish
  const { state, calls, html } = teamPage(t, { updateTeam: (id, data) => new Promise(resolve => { finish = () => resolve({ id, ...data }) }) })
  state.startTeamEdit()
  const pending = state.saveTeamInfo()
  assert.equal(state.savingTeamInfo.value, true)
  assert.ok((await html()).includes('保存中…'))
  await state.saveTeamInfo()
  state.cancelTeamEdit()
  assert.equal(calls.length, 1)
  assert.equal(state.editingTeamInfo.value, true)
  finish()
  await pending
  assert.equal(state.editingTeamInfo.value, false)
})

test('switching teams exits edit mode and a late save cannot switch the active team back', async t => {
  let finish
  const { state, auth } = teamPage(t, { updateTeam: (id, data) => new Promise(resolve => { finish = () => resolve({ id, ...data }) }) })
  state.startTeamEdit()
  state.editName.value = 'Saved old team'
  const pending = state.saveTeamInfo()
  await state.switchTeam(state.teams.value[1])
  await Vue.nextTick()
  assert.equal(state.editingTeamInfo.value, false)
  finish()
  await pending
  assert.equal(auth.currentTeamId, 2)
  assert.equal(auth.currentTeamName, 'Other team')
  assert.equal(state.editName.value, 'Other team')
  assert.equal(state.teams.value[0].name, 'Saved old team')
})

test('ordinary members cannot enter edit mode or save even through direct handler calls', async t => {
  const { state, calls } = teamPage(t, { role: 'member' })
  state.startTeamEdit()
  state.editingTeamId.value = 1
  await state.saveTeamInfo()
  assert.deepEqual(calls, [])
})

test('description boundaries retain input, count Unicode characters, and allow clearing', async t => {
  const { state, calls, messages } = teamPage(t)
  state.startTeamEdit()
  state.editDescription.value = '字'.repeat(501)
  await state.saveTeamInfo()
  assert.equal(calls.length, 0)
  assert.equal(state.editDescription.value.length, 501)
  assert.deepEqual(messages.at(-1), ['团队简介不能超过 500 个字符', 'error'])
  state.editDescription.value = '🧪'.repeat(500)
  assert.equal(state.descriptionLength.value, 500)
  await state.saveTeamInfo()
  assert.equal(calls[0].data.description, '🧪'.repeat(500))
  state.startTeamEdit()
  state.editDescription.value = ''
  await state.saveTeamInfo()
  assert.equal(calls[1].data.description, null)
})
