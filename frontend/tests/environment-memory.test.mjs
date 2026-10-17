import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createPinia, defineStore } from 'pinia'
import * as Vue from 'vue'
import { parse, compileScript } from '@vue/compiler-sfc'

const authSource = readFileSync(new URL('../src/stores/auth.js', import.meta.url), 'utf8')
  .replace(/^import .+$/gm, '').replace('export const useAuthStore', 'const useAuthStore')
const environmentSource = readFileSync(new URL('../src/composables/executionEnvironment.js', import.meta.url), 'utf8')
  .replace(/^import .+$/gm, '').replace('export function useExecutionEnvironment', 'function useExecutionEnvironment')
const rows = [{ id: 41, name: 'Local', base_url: 'http://local.invalid' }, { id: 42, name: 'Test', base_url: 'http://test.invalid' }]

function session(data = new Map(), { quota = false } = {}) {
  if (!data.has('wtp_user')) {
    data.set('wtp_user', 'alice')
    data.set('wtp_token', 'alice-token')
    data.set('wtp_pid', '10')
  }
  const storage = {
    getItem: key => data.get(key) ?? null,
    setItem(key, value) {
      if (quota && key === 'wtp_env_by_user_project') throw Error('Quota exceeded')
      data.set(key, String(value))
    },
    removeItem: key => data.delete(key),
  }
  const useStore = Function('defineStore', 'ref', 'listProjects', 'listTeams', 'localStorage', authSource + '\nreturn useAuthStore;')(
    defineStore, Vue.ref, async () => [], async () => [], storage)
  return { auth: useStore(createPinia()), data }
}

function environmentPage(t, auth, loader = async () => rows) {
  const useEnvironment = Function('computed', 'onScopeDispose', 'ref', 'watch', 'useAuthStore', 'listEnvironments',
    environmentSource + '\nreturn useExecutionEnvironment;')(
    Vue.computed, Vue.onScopeDispose, Vue.ref, Vue.watch, () => auth, loader)
  const scope = Vue.effectScope()
  t.after(() => scope.stop())
  return { ...scope.run(useEnvironment), dispose: () => scope.stop() }
}

test('environment preferences are isolated by account and project and survive relogin and reload', () => {
  const { auth, data } = session()
  auth.setPreferredEnv(10, 41)
  auth.setPreferredEnv(20, 52)
  auth.setAuth('bob-token', 'bob')
  auth.setPreferredEnv(10, 42)
  assert.equal(auth.getPreferredEnv(20), '')
  auth.logout()
  assert.equal(auth.getPreferredEnv(10), '')
  auth.setAuth('alice-new-token', 'ALICE')
  auth.setProject(10, 'Project')
  assert.equal(auth.getPreferredEnv(10), '41')
  assert.equal(auth.getPreferredEnv(20), '52')
  const reloaded = session(data).auth
  assert.equal(reloaded.getPreferredEnv(10), '41')
  reloaded.setAuth('bob-new-token', 'bob')
  assert.equal(reloaded.getPreferredEnv(10), '42')
})

test('new pages share selection, while explicitly choosing no environment stays unselected', async t => {
  const { auth } = session()
  const first = environmentPage(t, auth)
  await first.loadEnvironments()
  assert.equal(first.selectedEnv.value, '')
  first.selectedEnv.value = 41
  first.dispose()
  const second = environmentPage(t, auth)
  assert.equal(auth.getPreferredEnv(10), '41')
  await second.loadEnvironments()
  assert.equal(second.selectedEnv.value, '41')
  second.selectedEnv.value = ''
  const third = environmentPage(t, auth)
  await third.loadEnvironments()
  assert.equal(third.selectedEnv.value, '')
})

test('legacy unscoped preferences and corrupt storage do not leak a selection or break login', () => {
  for (const invalid of ['{broken', 'null', '[]', '{"alice":{"10":{"toString":null,"valueOf":null}}}']) {
    const data = new Map([['wtp_env_by_pid', '{"10":41}'], ['wtp_env_by_user_project', invalid]])
    const { auth } = session(data)
    assert.equal(auth.getPreferredEnv(10), '')
    auth.setPreferredEnv(10, 42)
    assert.equal(auth.getPreferredEnv(10), '42')
  }
})

test('a username matching an Object property is still isolated and storage quota preserves the session selection', () => {
  const { auth } = session(new Map(), { quota: true })
  auth.setAuth('constructor-token', 'constructor')
  assert.equal(auth.getPreferredEnv(10), '')
  auth.setPreferredEnv(10, 41)
  assert.equal(auth.getPreferredEnv(10), '41')
})

test('only a successful environment list clears a deleted or inaccessible saved environment', async t => {
  const { auth } = session()
  auth.setPreferredEnv(10, 99)
  const page = environmentPage(t, auth)
  assert.equal(auth.getPreferredEnv(10), '99')
  await page.loadEnvironments()
  assert.equal(page.selectedEnv.value, '')
  assert.equal(auth.getPreferredEnv(10), '')
})

test('failed or malformed environment loads retain the preference for a later retry', async t => {
  const { auth } = session()
  auth.setPreferredEnv(10, 41)
  let result = 'offline'
  const page = environmentPage(t, auth, async () => {
    if (result === 'offline') throw Error('Offline')
    return result
  })
  await assert.rejects(page.loadEnvironments(), /Offline/)
  assert.equal(auth.getPreferredEnv(10), '41')
  result = { invalid: true }
  await assert.rejects(page.loadEnvironments(), /环境列表格式错误/)
  assert.equal(auth.getPreferredEnv(10), '41')
  result = rows
  await page.loadEnvironments()
  assert.equal(page.selectedEnv.value, '41')
})

test('a late old-project response cannot clear the newly selected project preference', async t => {
  const { auth } = session()
  let finish
  const page = environmentPage(t, auth, () => new Promise(resolve => { finish = resolve }))
  const pending = page.loadEnvironments()
  auth.setProject(20, 'Other project')
  auth.setPreferredEnv(20, 52)
  finish(rows)
  await pending
  assert.deepEqual(page.envs.value, [])
  assert.equal(auth.getPreferredEnv(20), '52')
})

test('a late old-account response cannot overwrite another account selection', async t => {
  const { auth } = session()
  auth.setPreferredEnv(10, 41)
  let finish
  const page = environmentPage(t, auth, () => new Promise(resolve => { finish = resolve }))
  const pending = page.loadEnvironments()
  auth.setAuth('bob-token', 'bob')
  auth.setProject(10, 'Project')
  auth.setPreferredEnv(10, 42)
  finish([{ id: 41 }])
  await pending
  assert.equal(auth.getPreferredEnv(10), '42')
  assert.deepEqual(page.envs.value, [])
  auth.setAuth('alice-again', 'alice')
  assert.equal(auth.getPreferredEnv(10), '41')
})

test('an unmounted page cannot clear the environment chosen on the next page', async t => {
  const { auth } = session()
  let finish
  const old = environmentPage(t, auth, () => new Promise(resolve => { finish = resolve }))
  const pending = old.loadEnvironments()
  old.dispose()
  const current = environmentPage(t, auth)
  await current.loadEnvironments()
  current.selectedEnv.value = 42
  finish([{ id: 41 }])
  await pending
  assert.equal(current.selectedEnv.value, '42')
  assert.equal(auth.getPreferredEnv(10), '42')
})

test('overlapping environment loads apply only the latest response', async t => {
  const { auth } = session()
  const finish = []
  const page = environmentPage(t, auth, () => new Promise(resolve => finish.push(resolve)))
  const first = page.loadEnvironments()
  const second = page.loadEnvironments()
  finish[1]([{ id: 42 }])
  await second
  page.selectedEnv.value = 42
  finish[0]([{ id: 41 }])
  await first
  assert.equal(page.selectedEnv.value, '42')
})

for (const view of ['Interfaces', 'Cases', 'Orchestration', 'Regression']) {
  test(`the actual ${view} page restores, saves, and remounts with the shared environment`, async t => {
    const { auth } = session()
    auth.setPreferredEnv(10, 41)
    const descriptor = parse(readFileSync(new URL(`../src/views/${view}.vue`, import.meta.url), 'utf8')).descriptor
    const script = compileScript(descriptor, { id: 'environment-page-' + view })
    const names = Object.keys(script.imports)
    const code = script.content.replace(/^import[\s\S]*?\bfrom\s*['"][^'"]+['"];?/gm, '').replace('export default', 'return')
    async function mount() {
      const scope = Vue.effectScope()
      t.after(() => scope.stop())
      const mocks = { ...Vue, onMounted() {}, onUnmounted() {},
        useFeedback: () => ({ showMessage() {}, confirmAction: async () => false }), useRouter: () => ({ push() {} }),
        useExecutionEnvironment: () => environmentPage(t, auth),
      }
      const component = Function(...names, code)(...names.map(name => mocks[name] || (script.imports[name].source.includes('/api/') ? async () => [] : {})))
      const state = scope.run(() => component.setup({}, { expose() {} }))
      await (view === 'Regression' ? state.loadEnvs() : state.load())
      return { state, dispose: () => scope.stop() }
    }
    const first = await mount()
    assert.equal(first.state.selectedEnv.value, '41')
    first.state.selectedEnv.value = 42
    assert.equal(auth.getPreferredEnv(10), '42')
    first.dispose()
    const second = await mount()
    assert.equal(second.state.selectedEnv.value, '42')
  })
}
