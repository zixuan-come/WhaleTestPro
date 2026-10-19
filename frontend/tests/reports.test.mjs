import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import * as Vue from 'vue'
import { parse, compileScript } from '@vue/compiler-sfc'
import { preferredReportType, rememberReportType, REPORT_TYPES } from '../src/utils/reportPreferences.js'

const descriptor = parse(readFileSync(new URL('../src/views/Reports.vue', import.meta.url), 'utf8')).descriptor
const compiled = compileScript(descriptor, { id: 'reports-contract' })
const script = compiled.content.replace(/^import[\s\S]*?\bfrom\s*['"][^'"]+['"];?/gm, '').replace('export default', 'return')
const page = (id = 'run-1') => ({ items: [{ id, name: id, kind: 'case', passed: true, status: 'completed' }], page: 1, page_size: 20,
  total: 1, total_pages: 1, passed_count: 1, failed_count: 0, running_count: 0, pass_rate: 1 })
const deferred = () => { let resolve; return { promise: new Promise(r => resolve = r), resolve: value => resolve(value) } }
function view(t, request = async () => page(), route = { query: {} }, options = {}) {
  const callbacks = [], calls = [], mutations = [], messages = [], folderRows = [{id:1,name:'本轮验收',count:0}]
  const auth = Vue.reactive({username:'report-a',currentProjectId:1,token:'synthetic'})
  const mocks = {...Vue,onMounted(){},onBeforeUnmount(callback){callbacks.push(callback)},
    listExecutionReports:params=>{calls.push(params);return request(params)},useAuthStore:()=>auth,
    formatShanghaiDateTime:value=>value,preferredReportType,rememberReportType,REPORT_TYPES,
    ReportExecutionDetail:null,Modal:null,SuiteFilterSelect:null,useRoute:()=>route,
    useFeedback:()=>({notice:Vue.ref(null),showMessage:(...args)=>messages.push(args),confirmAction:(...args)=>options.confirm?options.confirm(...args):Promise.resolve(true),resolveConfirm(){}}),
    listReportFolders:async()=>({items:[...folderRows],total:1,unfiled:1,can_manage:true}),
    createReportFolder:async data=>{mutations.push(['create',data]);const row={id:2,...data,count:0};folderRows.push(row);return row},
    renameReportFolder:async(id,data)=>{mutations.push(['rename',id,data]);Object.assign(folderRows.find(row=>row.id===id),data);return{id,...data}},
    deleteReportFolder:async id=>{mutations.push(['folder-delete',id]);folderRows.splice(folderRows.findIndex(row=>row.id===id),1);return{deleted:1,unfiled:1}},
    moveExecutionReports:async data=>{mutations.push(['move',data]);return{moved:data.report_ids.length}},
    deleteExecutionReport:async id=>{mutations.push(['delete',id]);return{deleted:1}},
    deleteExecutionReports:async data=>{mutations.push(['batch-delete',data]);return{deleted:data.report_ids.length}},...options.api}
  const names=Object.keys(compiled.imports),component=Function(...names,script)(...names.map(name=>mocks[name]))
  const scope=Vue.effectScope(),state=scope.run(()=>component.setup({},{expose(){}}))
  t.after(()=>{callbacks.forEach(callback=>callback());scope.stop()})
  return{state,auth,calls,callbacks,mutations,messages,folderRows}
}

test('report preferences survive reload and remain isolated by account and project', () => {
  const values = new Map(), storage = { getItem: key => values.get(key), setItem: (key, value) => values.set(key, value) }
  rememberReportType('a', 1, 'suite', storage)
  rememberReportType('b', 1, 'regression', storage)
  assert.equal(preferredReportType('a', 1, storage), 'suite')
  assert.equal(preferredReportType('b', 1, storage), 'regression')
  assert.equal(preferredReportType('a', 2, storage), 'all')
  assert.equal(preferredReportType('', 1, storage), 'all')
  assert.equal(preferredReportType('a', 1, { getItem: () => 'broken' }), 'all')
  assert.equal(preferredReportType('a', 1, { getItem() { throw Error('disabled') } }), 'all')
  assert.doesNotThrow(() => rememberReportType('a', 1, 'case', { setItem() { throw Error('quota') } }))
})

test('a scheduled task report link selects its category and applies its name filter', async t => {
  const { state, calls } = view(t, async () => page(), { query: { kind: 'regression', q: '每日订单回归' } })
  state.initialize()
  await Vue.nextTick()
  assert.equal(state.reportType.value, 'regression')
  assert.equal(state.search.value, '每日订单回归')
  assert.equal(calls.at(-1).q, '每日订单回归')
})

test('switching categories cannot display a late response from another category', async t => {
  const first = deferred(), second = deferred()
  const { state } = view(t, params => params.kind === 'suite' ? second.promise : first.promise)
  const old = state.load(1)
  state.switchType('suite')
  second.resolve(page('run-suite'))
  await Vue.nextTick(); await new Promise(resolve => setImmediate(resolve))
  first.resolve(page('run-old'))
  await old
  assert.equal(state.items.value[0].id, 'run-suite')
  assert.equal(state.reportType.value, 'suite')
})

test('search, status and date filters are sent to the server before pagination', async t => {
  const { state, calls } = view(t)
  state.search.value = '  跨页名称  '; state.statusFilter.value = 'failed'
  state.dateFrom.value = '2026-10-18'; state.dateTo.value = '2026-10-19'
  await state.load(3)
  assert.deepEqual(calls[0], { kind: 'all', page: 3, page_size: 20, folder_id: undefined, q: '跨页名称',
    status: 'failed', date_from: '2026-10-18', date_to: '2026-10-19' })
})

test('changing projects invalidates old requests and resets filters', async t => {
  const old = deferred()
  const { state, auth, calls } = view(t, () => calls.length === 1 ? old.promise : Promise.resolve(page('run-new-project')))
  const pending = state.load(1)
  state.search.value = 'old search'
  auth.currentProjectId = 2
  await Vue.nextTick(); await new Promise(resolve => setImmediate(resolve))
  old.resolve(page('run-old-project')); await pending
  assert.equal(state.items.value[0].id, 'run-new-project')
  assert.equal(state.search.value, '')
})

test('logout clears report data and counts without sending requests', async t => {
  const { state, auth, calls } = view(t)
  await state.load(1)
  auth.token = ''; auth.currentProjectId = null
  await Vue.nextTick()
  assert.deepEqual(state.items.value, [])
  assert.equal(state.passedTotal.value, 0)
  assert.equal(state.reportTotal.value, 0)
  assert.equal(calls.length, 1)
})

test('unmount prevents an outstanding response from restoring report rows', async t => {
  const result = deferred(), { state, callbacks } = view(t, () => result.promise)
  const pending = state.load(1)
  callbacks.forEach(callback => callback())
  result.resolve(page('run-late')); await pending
  assert.deepEqual(state.items.value, [])
})

test('a regression result link opens its exact report even outside the first page and clears on project change', async t => {
  const { state, auth } = view(t, async () => page('run-2'), { query: { kind: 'regression', report: 'run-999' } })
  state.initialize()
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(state.reportType.value, 'regression')
  assert.equal(state.linkedReportId.value, 'run-999')
  auth.currentProjectId = 2
  await Vue.nextTick()
  assert.equal(state.linkedReportId.value, null)
})

test('folder creation validates names, selects the saved folder and keeps failed drafts', async t => {
  const {state,mutations,calls}=view(t)
  await state.loadFolders();state.editFolder()
  assert.ok(state.folderForm.value.name.endsWith('-report-a'))
  state.folderForm.value.name=' ';await state.saveFolder();assert.equal(mutations.length,0)
  state.folderForm.value.name='  本日验收  ';await state.saveFolder()
  assert.deepEqual(mutations[0],['create',{name:'本日验收'}])
  assert.equal(state.selectedFolder.value,'2');assert.equal(calls.at(-1).folder_id,2)
  const bad=view(t,undefined,undefined,{api:{createReportFolder:async()=>{throw Error('同名目录')}}})
  await bad.state.loadFolders();bad.state.editFolder();bad.state.folderForm.value.name='保留草稿'
  await bad.state.saveFolder();assert.equal(bad.state.folderForm.value.name,'保留草稿');assert.equal(bad.state.formError.value,'同名目录')
})

test('selection survives pagination and moves all explicitly selected report types', async t => {
  const {state,mutations}=view(t,async params=>({...page(`run-${params.page}`),page:params.page,total:2,total_pages:2}))
  await state.loadFolders();await state.load(1);state.togglePage();await state.load(2);state.togglePage()
  assert.deepEqual(state.chosenIds.value,['run-1','run-2'])
  state.openMove(state.chosenIds.value);state.moveTarget.value='1';await state.saveMove()
  assert.deepEqual(mutations[0],['move',{report_ids:['run-1','run-2'],folder_id:1}])
  assert.equal(state.chosenIds.value.length,0);assert.equal(state.moveForm.value,null)
})

test('directory deletion asks to retain reports and returns the active view to unfiled', async t => {
  const notices=[]
  const {state,mutations,calls}=view(t,undefined,undefined,{confirm:async message=>{assert.equal(state.notice.value,null);notices.push(message);return true}})
  await state.loadFolders();state.selectFolder(1)
  state.notice.value={message:'已移动报告',type:'success'}
  await state.removeFolder({id:1,name:'本轮验收'})
  assert.match(notices[0],/报告内容保留/);assert.deepEqual(mutations[0],['folder-delete',1])
  assert.equal(state.selectedFolder.value,'0');assert.equal(calls.at(-1).folder_id,0)
})

test('deleting the last result on a page clamps pagination and clears selected reports', async t => {
  let deleted=false
  const {state,calls}=view(t,async params=>deleted?{...page('run-1'),items:params.page===1?page().items:[],page:params.page,total:1,total_pages:1}:{...page('run-2'),page:2,total:2,total_pages:2},undefined,
    {api:{deleteExecutionReport:async()=>{deleted=true;return{deleted:1}}}})
  await state.loadFolders();await state.load(2);state.togglePage();await state.removeReports([...state.chosen.value.values()])
  assert.equal(state.page.value,1);assert.equal(state.items.value[0].id,'run-1');assert.equal(state.chosenIds.value.length,0)
  assert.deepEqual(calls.slice(-2).map(call=>call.page),[2,1])
})

test('running reports cannot be deleted and denied users cannot trigger writes programmatically', async t => {
  const normal=view(t);await normal.state.loadFolders()
  await normal.state.removeReports([{id:'run-1',passed:null,status:'running'}]);assert.equal(normal.mutations.length,0)
  const denied=view(t,undefined,undefined,{api:{listReportFolders:async()=>({items:[],total:0,unfiled:0,can_manage:false})}})
  await denied.state.loadFolders();denied.state.editFolder();denied.state.toggleReport(page().items[0]);denied.state.openMove(['run-1'])
  await denied.state.removeReports(page().items);assert.equal(denied.mutations.length,0)
  assert.equal(denied.state.folderForm.value,null);assert.equal(denied.state.moveForm.value,null);assert.equal(denied.state.chosenIds.value.length,0)
})

test('changing project during confirmation, even away and back, cannot delete stale selections', async t => {
  const decision=deferred(),{state,auth,mutations}=view(t,undefined,undefined,{confirm:()=>decision.promise})
  await state.loadFolders();const pending=state.removeReports(page().items)
  auth.currentProjectId=2;auth.currentProjectId=1
  await Vue.nextTick();decision.resolve(true);await pending
  assert.equal(mutations.length,0);assert.equal(state.confirming.value,false)
})

test('late folder loads and mutations cannot restore another project or a closed modal', async t => {
  const response=deferred(),{state,auth,messages}=view(t,undefined,undefined,{api:{createReportFolder:()=>response.promise}})
  await state.loadFolders();state.editFolder();state.folderForm.value.name='旧项目目录'
  const pending=state.saveFolder();auth.currentProjectId=2;await Vue.nextTick()
  response.resolve({id:99,name:'旧项目目录'});await pending
  assert.equal(state.selectedFolder.value,'all');assert.equal(state.folderForm.value,null);assert.equal(messages.length,0)
  const folders=deferred(),another=view(t,undefined,undefined,{api:{listReportFolders:()=>folders.promise}})
  const load=another.state.loadFolders();another.callbacks.forEach(callback=>callback())
  folders.resolve({items:[{id:99,name:'晚到目录'}],total:1,unfiled:0,can_manage:true});await load
  assert.deepEqual(another.state.folders.value,[])
})

test('folder/filter changes clear hidden selections and failed deletions retain the chosen reports', async t => {
  const {state,messages}=view(t,undefined,undefined,{api:{deleteExecutionReport:async()=>{throw Error('报告仍在执行')}}})
  await state.loadFolders();await state.load(1);state.togglePage()
  await state.removeReports([...state.chosen.value.values()]);assert.equal(state.chosenIds.value.length,1);assert.match(messages[0][0],/仍在执行/)
  state.selectFolder(1);assert.equal(state.chosenIds.value.length,0)
  state.toggleReport(page().items[0]);state.filtersChanged();assert.equal(state.chosenIds.value.length,0)
})
