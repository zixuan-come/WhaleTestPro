import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {parse,compileScript} from '@vue/compiler-sfc'
import * as Vue from 'vue'
import { extractRuleRows, serializeExtractRules } from '../src/utils/extractRules.js'
import { assertionRows, serializeAssertions } from '../src/utils/assertionRules.js'
const descriptor=parse(readFileSync(new URL('../src/views/Perf.vue',import.meta.url),'utf8')).descriptor
const code=compileScript(descriptor,{id:'perf-live-test'}).content.replace(/^import[\s\S]*?from\s*['"][^'"]+['"];?\s*$/gm,'').replace('export default','return')
const tick=()=>new Promise(resolve=>setImmediate(resolve))
const task=(status='running',count=10)=>({id:1,name:'订单压测',status,users:2,duration:30,rps:5,request_stats:[{num_requests:count,num_failures:1}],history_samples:[{elapsed_s:2,rps:5,users:2},{elapsed_s:4,rps:5,users:2}]})
function view(t,overrides={}){
 const auth=Vue.reactive({currentProjectId:1}),timers=new Map(),cleanups=[],data={rows:[task('pending')],fail:false},calls=[]
 const params={Vue:{...Vue,onUnmounted:fn=>cleanups.push(fn)},useAuthStore:()=>auth,useFeedback:()=>({showMessage(){},confirmAction:async()=>true}),listPerfTasks:async()=>{calls.push('list');if(overrides.list)return overrides.list();if(data.fail)throw Error('offline');return data.rows},createPerfTask:async()=>{},deletePerfTask:async()=>{},runPerfTask:async()=>{calls.push('run');data.rows=[task()];return task('queued')},stopPerfTask:async()=>{calls.push('stop');return task('cancelled',20)},listInterfaces:async()=>[],listCases:async()=>[],listScenarios:async()=>[],listEnvironments:async()=>[],METHODS:[],newPerfStep:()=>({}),scenarioSteps:()=>[],buildPerfPlan:()=>({}),EnvironmentSelect:null,Modal:null,setInterval:fn=>{timers.set(1,fn);return 1},clearInterval:id=>timers.delete(id)}
 Object.assign(params,{extractRuleRows,assertionRows,AssertionEditor:null,PERF_EXTRACT_OPTIONS:{},ExtractRulesEditor:null,updatePerfTask:async()=>{},listPerfRuns:async()=>({total:0,items:[]}),getPerfRun:async()=>({result:{...task('done',100),users:2}}),clearPerfRuns:async()=>({deleted:1})},overrides.api||{})
 const options=Function(...Object.keys(params),'const {ref,reactive,computed,onUnmounted,watch}=Vue;'+code)(...Object.values(params))
 const scope=Vue.effectScope(),state=scope.run(()=>options.setup({}, {expose(){}}))
 t.after(()=>{cleanups.forEach(fn=>fn());scope.stop()});return {state,auth,data,timers,calls}
}
test('starting opens live results, successive polls update metrics, terminal results stop polling',async t=>{
 const {state,data,timers}=view(t);await tick();await state.onRun(task('pending'));await tick()
 assert.equal(state.showDetail.value,true);assert.equal(state.detailLive.value,true);assert.equal(timers.size,1)
 data.rows=[task('running',50)];await state.refresh();assert.equal(state.requestTotals.value.requests,50)
 data.rows=[task('done',100)];await state.refresh();await tick()
 assert.equal(state.requestTotals.value.requests,100);assert.equal(state.detailLive.value,false);assert.equal(timers.size,0)
})
test('poll errors retain latest metrics and recover visibly on next success',async t=>{
 const {state,data}=view(t);await tick();state.openDetail(task());data.fail=true;await state.refresh()
 assert.equal(state.requestTotals.value.requests,10);assert.match(state.pollError.value,/刷新失败/)
 data.fail=false;data.rows=[task('running',30)];await state.refresh();assert.equal(state.pollError.value,'');assert.equal(state.requestTotals.value.requests,30)
})
test('slow polls never overlap and an older project cannot replace current results',async t=>{
 let resolve,count=0
 const {state,auth}=view(t,{list:async()=>{count++;return count===2?new Promise(r=>resolve=r):[task()]}});await tick()
 const pending=state.refresh();await state.refresh();assert.equal(count,2)
 auth.currentProjectId=2;await tick();resolve([{...task(),id:99}]);await pending
 assert.equal(state.items.value[0].id,1);assert.equal(state.showDetail.value,false)
})
test('stopping updates open results immediately and blocks an older in-flight running response',async t=>{
 let resolve,count=0
 const {state}=view(t,{list:async()=>++count===2?new Promise(r=>resolve=r):[task()]});await tick();state.openDetail(task())
 const pending=state.refresh();await state.onStop(task());resolve([task('running',99)]);await pending
 assert.equal(state.detailTask.value.status,'cancelled');assert.equal(state.requestTotals.value.requests,20)
})

test('historical results keep the execution snapshot while the task config and current run differ',async t=>{
 const {state,data}=view(t);await tick()
 await state.openLatestResult({...task('done'),latest_run_id:7,users:20})
 assert.equal(state.detailTask.value.users,2)
 data.rows=[{...task('running',300),celery_task_id:'new-run'}];await state.refresh()
 assert.equal(state.requestTotals.value.requests,100)
 state.openDetail({...task('running',50),celery_task_id:'old-run'});await state.refresh()
 assert.equal(state.requestTotals.value.requests,50)
})

test('history discards a slow previous project response',async t=>{
 let resolve
 const {state,auth}=view(t,{api:{listPerfRuns:()=>new Promise(r=>resolve=r)}});await tick()
 state.openHistory(task('done'));auth.currentProjectId=2;await tick()
 resolve({total:10,items:[{id:99}]});await tick()
 assert.equal(state.showHistory.value,false);assert.equal(state.historyRows.value.length,0)
})

test('configuration editing preserves raw body and declarative step settings',async t=>{
 const {state}=view(t);await tick()
 const step={name:'submit',method:'POST',path:'/orders',headers:{'Content-Type':'text/plain'},params:{id:1},body_type:'raw',body:'not json',extract_rules:{id:'$.id'},assertions:[{type:'json_eq',path:'$.ok',expected:true}],expected_status:201,allow_redirects:false}
 state.openEdit({...task('done'),load_config:{mode:'single',steps:[step],variables:{token:'x'},datasets:[],timeout_seconds:10,wait_seconds:2,stop_on_failure:true}})
 assert.equal(state.steps.value[0].body,'not json');assert.equal(state.steps.value[0].body_type,'raw')
 assert.deepEqual(serializeAssertions(state.steps.value[0].assertions),step.assertions)
 assert.deepEqual(JSON.parse(state.steps.value[0].params),{id:1})
 assert.deepEqual(serializeExtractRules(state.steps.value[0].extract_rules),step.extract_rules)
 assert.equal(state.form.timeout_seconds,10);assert.equal(state.editingId.value,1)
})

test('TPS separates average, successful and the latest sampling interval',async t=>{
 const {state}=view(t);await tick()
 state.openDetail({...task('done'),load_config:{mode:'chain'},iteration_stats:{iterations:100,failures:10,elapsed_seconds:10,iteration_rps:10},history_samples:[{elapsed_s:10,tps:20}]})
 assert.equal(state.transactionStats.value.average,10);assert.equal(state.transactionStats.value.success,9)
 assert.equal(state.transactionStats.value.current,20);assert.equal(state.transactionStats.value.failRatio,.1)
 state.openDetail(task('done'));assert.equal(state.transactionStats.value,null)
})
