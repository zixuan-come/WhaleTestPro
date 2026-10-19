import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import * as Vue from 'vue'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import { caseToStep, savedScenarioSteps, equivalentCaseIds } from '../src/utils/scenarioSteps.js'
import { cloneRequest, requestDraft, serializeRequest } from '../src/utils/requestConfig.js'
import { scenarioSteps } from '../src/utils/perf-plan.js'
import { suiteCatalog, selectedSuiteContent } from '../src/utils/suiteSelection.js'

const request = { id:10, name:'查询订单', method:'GET', url:'/orders/{id}', path_params:{id:'${order_id}'}, headers:{'X-Project-Id':'1'}, params:null, body:null }
const template = { id:1, name:'查询订单 - 成功', interface_id:10, expected_status:200, extract_rules:null, assertions:[{type:'json_eq',path:'$.id',expected:42}], retries:0 }

function compiled(path) {
  const descriptor = parse(readFileSync(new URL(path, import.meta.url), 'utf8')).descriptor
  const script = compileScript(descriptor, { id:path })
  assert.deepEqual(compileTemplate({source:descriptor.template.content,id:path,compilerOptions:{bindingMetadata:script.bindings}}).errors, [])
  const code = script.content.replace(/^import[\s\S]*?\bfrom\s*['"][^'"]+['"];?/gm,'').replace('export default','return')
  return (t, props, mocks) => {
    const names = Object.keys(script.imports)
    const component = Function(...names,code)(...names.map(name=>mocks[name] ?? Vue[name]))
    const scope = Vue.effectScope();t.after(()=>scope.stop())
    return scope.run(()=>component.setup(props,{expose(){},emit:mocks.emit || (()=>{})}))
  }
}
const setup = compiled('../src/views/Orchestration.vue')
const editorSetup = compiled('../src/components/ScenarioStepEditor.vue')
const pickerSetup = compiled('../src/components/ScenarioCasePicker.vue')

async function page(t, overrides={}) {
  const calls=[], messages=[]
  let saved={id:5,name:'订单核心链路',description:null,case_ids:[1,1],steps:[caseToStep(template,request),caseToStep(template,request)]}
  const mocks={onMounted(){},useAuthStore:()=>Vue.reactive({token:'test-session',currentProjectId:1}),caseToStep,savedScenarioSteps,cloneRequest,
    useFeedback:()=>({showMessage:(...args)=>messages.push(args),confirmAction:async()=>true}),
    useExecutionEnvironment:()=>({envs:Vue.ref([]),selectedEnv:Vue.ref(3),loadEnvironments:async()=>{}}),
    listScenarios:async()=>[cloneRequest(saved)],listCases:async()=>[cloneRequest(template)],listInterfaces:async()=>[cloneRequest(request)],
    getScenario:async()=>cloneRequest(saved),getCase:async()=>({...cloneRequest(template),name:'最新模板'}),getInterface:async()=>cloneRequest(request),
    updateScenario:async(id,payload)=>{calls.push(['save',id,cloneRequest(payload)]);saved={id,...cloneRequest(payload),case_ids:payload.steps.map(step=>step.source_case_id)};return cloneRequest(saved)},
    runScenario:async(...args)=>{calls.push(['run',...args]);return []},...overrides}
  const state=setup(t,{},mocks);await state.load();await state.selectScenario(saved)
  return {state,calls,messages,mocks}
}

test('each template occurrence owns nested request/assertion values and a stable identifier',()=>{
  const a=caseToStep(template,request),b=caseToStep(template,request)
  assert.notEqual(a.step_id,b.step_id)
  a.path_params.id='999';a.assertions[0].expected=999
  assert.equal(b.path_params.id,'${order_id}');assert.equal(template.assertions[0].expected,42)
  const cleared=caseToStep({...template,request_overrides:{headers:null,params:{page:2}}},request)
  assert.equal(cleared.headers,null);assert.deepEqual(cleared.params,{page:2})
})

test('editing and reopening persists different expectations and parameters for the same source',async t=>{
  const {state,calls}=await page(t)
  const original=cloneRequest(state.chain.value[0])
  state.editStep(state.chain.value[1])
  state.editingStep.value.name='订单不存在';state.editingStep.value.expected_status=404;state.editingStep.value.path_params.id='999'
  assert.equal(state.dirty.value,false) // Modal draft is separate until applied.
  state.applyStep(state.editingStep.value)
  assert.equal(state.dirty.value,true);assert.deepEqual(cloneRequest(state.chain.value[0]),original)
  await state.saveCurrent();assert.equal(state.dirty.value,false)
  assert.ok(!Object.hasOwn(calls[0][2],'case_ids'))
  await state.selectScenario({id:5})
  assert.equal(state.chain.value[1].expected_status,404);assert.equal(state.chain.value[1].path_params.id,'999')
})

test('reapplying a fresh template stays in the editor until applied and touches only that occurrence',async t=>{
  const {state}=await page(t)
  const key=state.chain.value[1].step_id, first=cloneRequest(state.chain.value[0])
  state.chain.value[1].expected_status=404
  state.editStep(state.chain.value[1])
  await state.reapplyTemplate(state.chain.value[1])
  assert.equal(state.chain.value[1].expected_status,404)
  assert.equal(state.editingStep.value.name,'最新模板')
  state.editingStep.value=null // Cancel also discards a newly loaded template.
  assert.equal(state.chain.value[1].expected_status,404)
  state.editStep(state.chain.value[1])
  await state.reapplyTemplate(state.editingStep.value)
  state.applyStep(state.editingStep.value)
  assert.equal(state.chain.value[1].name,'最新模板');assert.equal(state.chain.value[1].expected_status,200)
  assert.equal(state.chain.value[1].step_id,key);assert.deepEqual(cloneRequest(state.chain.value[0]),first)
})

test('case picker searches names and paths, retains cross-page selection order, and limits additions',t=>{
  const cases=Array.from({length:25},(_,i)=>({...template,id:i+1,name:`查询订单 ${i+1}`,interface_id:i===24?20:10}))
  const interfaces=[request,{...request,id:20,name:'健康检查',url:'/health'}],events=[]
  const state=pickerSetup(t,{cases,interfaces,remaining:2},{emit:(...args)=>events.push(args)})
  assert.equal(state.pages.value,2);assert.equal(state.visible.value.length,20)
  state.toggle(2);state.page.value=2;state.toggle(25)
  state.query.value='/health'
  assert.equal(state.page.value,1);assert.deepEqual(state.filtered.value.map(item=>item.id),[25])
  state.query.value='';state.interfaceId.value=10
  assert.equal(state.filtered.value.length,24)
  state.add();assert.deepEqual(events[0][1].map(item=>item.id),[2,25])
  state.toggle(3);state.add();assert.equal(events.length,1);assert.equal(state.tooMany.value,true)
  state.chosenIds.value=[];state.togglePage();assert.equal(state.chosenIds.value.length,20)
  state.togglePage();assert.equal(state.chosenIds.value.length,0)
})

test('batch additions create independent copies again and preserve keyboard and drag ordering',async t=>{
  const {state}=await page(t)
  state.openCasePicker();state.addCases([template]);assert.equal(state.showCasePicker.value,false)
  state.openCasePicker();state.addCases([template]);assert.equal(state.chain.value.length,4)
  assert.equal(new Set(state.chain.value.map(step=>step.step_id)).size,4)
  const ids=state.chain.value.map(step=>step.step_id)
  state.moveStep(3,-1);assert.equal(state.chain.value[2].step_id,ids[3])
  state.onDragStart(2);state.onDrop(0);assert.equal(state.chain.value[0].step_id,ids[3])
  state.chain.value[0].path_params.id='999';assert.equal(state.chain.value[3].path_params.id,'${order_id}')
  state.scenarioSearch.value='核心';assert.equal(state.filteredScenarios.value.length,1)
  state.scenarioSearch.value='不存在';assert.equal(state.filteredScenarios.value.length,0)
})

test('a failed template refresh leaves the editor draft intact',async t=>{
  const {state}=await page(t,{getCase:async()=>{throw Error('来源用例已删除')}})
  state.editStep(state.chain.value[1]);state.editingStep.value.expected_status=404
  await state.reapplyTemplate(state.editingStep.value)
  assert.equal(state.editingStep.value.expected_status,404);assert.equal(state.chain.value[1].expected_status,200)
  assert.equal(state.refreshing.value,false)
})

test('running a dirty scenario saves the actual steps before executing; failed save never executes',async t=>{
  const {state,calls}=await page(t)
  state.chain.value[1].expected_status=404
  await state.onRun();assert.deepEqual(calls.map(row=>row[0]),['save','run'])
  const bad=await page(t,{updateScenario:async()=>{throw Error('保存失败')}})
  bad.state.chain.value[0].name='未保存'
  await bad.state.onRun();assert.equal(bad.calls.length,0);assert.equal(bad.state.dirty.value,true)
})

test('removed legacy references stay visible and disabled instead of silently disappearing',()=>{
  const steps=savedScenarioSteps({case_ids:[1,999,1]},[template],[request])
  assert.equal(steps.length,3);assert.ok(steps[1].missing_reason)
  assert.notEqual(steps[0].step_id,steps[2].step_id)
})

test('step editor cancels safely, rejects invalid JSON and applies independent request values',t=>{
  const step=caseToStep(template,request),events=[]
  const state=editorSetup(t,{step},{onBeforeUnmount(){},cloneRequest,requestDraft,serializeRequest,emit:(...args)=>events.push(args)})
  assert.equal(state.advanced.value,false)
  state.expectedStatus.value=404;state.request.value.pathParams.id='999';state.assertions.value='invalid'
  state.apply();assert.ok(state.error.value.includes('JSON'));assert.equal(events.length,0);assert.equal(state.advanced.value,true)
  state.assertions.value='[]';state.apply()
  assert.equal(events[0][1].expected_status,404);assert.equal(events[0][1].path_params.id,'999')
  assert.equal(step.expected_status,200);assert.equal(step.path_params.id,'${order_id}')
})

test('editing only status preserves untouched typed Query and Body values',t=>{
  const step={...caseToStep(template,request),params:{page:2,enabled:false,filters:['paid']},body:{quantity:2}},events=[]
  const state=editorSetup(t,{step},{onBeforeUnmount(){},cloneRequest,requestDraft,serializeRequest,emit:(...args)=>events.push(args)})
  state.expectedStatus.value=404;state.apply()
  assert.deepEqual(events[0][1].params,step.params);assert.deepEqual(events[0][1].body,step.body)
})

test('performance import uses saved per-step configuration even after the library case is deleted',()=>{
  const a=caseToStep(template,request),b=caseToStep(template,request)
  b.expected_status=404;b.path_params.id='999';b.name='删除后查询';b.assertions=[]
  const steps=scenarioSteps({steps:[a,b],case_ids:[1,1]},[],[{...request,url:'/changed'}])
  assert.deepEqual(steps.map(step=>step.expected_status),[200,404])
  assert.deepEqual(steps.map(step=>step.path),['/orders/${order_id}','/orders/999'])
  assert.equal(steps[1].name,'删除后查询')
  assert.equal(scenarioSteps({steps:[a]},[],[])[0].path,'/orders/${order_id}')
  assert.throws(()=>scenarioSteps({steps:[{...a,retries:1}]},[],[request]),/重试/)
})

test('suite coverage excludes modified copies but still deduplicates an unchanged source',()=>{
  const a=caseToStep(template,request),b={...caseToStep(template,request),expected_status:404}
  assert.deepEqual([...equivalentCaseIds([a],[template],[request])],[1])
  assert.deepEqual([...equivalentCaseIds([b],[template],[request])],[])
  const catalog=suiteCatalog([{id:5,name:'差异场景',steps:[b],case_ids:[1]}],[template],[request])
  const chosen=selectedSuiteContent(catalog,{scenario_ids:[5],case_ids:[1]})
  assert.equal(chosen.cases[0].included,false);assert.equal(catalog.scenarios[0].steps[0].name,b.name)
})

function debugEditor(t, overrides={}) {
  const events=[],calls=[],props=Vue.reactive({step:caseToStep(template,request),scenarioId:5,envId:3,
    sessionId:'',variables:{},debugMode:true})
  let dispose=()=>{}
  const mocks={cloneRequest,requestDraft,serializeRequest,onBeforeUnmount(fn){dispose=fn},
    emit(name,value){events.push([name,value]);if(name==='debug'){props.debugResult=value;props.sessionId=value.session_id;props.variables=value.variables}},
    debugScenarioStep:async(...args)=>{calls.push(args);return{step_id:props.step.step_id,session_id:'a'.repeat(32),response_id:'b'.repeat(32),actual_status:201,expected_status:200,passed:false,response_detail:{status_code:201,headers:{},body:{id:42}},variables:{}}},
    validateScenarioExtraction:async(...args)=>{calls.push(['extract',...args]);return{step_id:props.step.step_id,session_id:'a'.repeat(32),extraction:[{name:'order_id',passed:true,value:42}],variables:{order_id:42}}},...overrides}
  return {state:editorSetup(t,props,mocks),props,events,calls,dispose:()=>dispose()}
}

test('single-step debug executes the current unsaved draft and keeps it separate from apply',async t=>{
  const {state,props,calls,events}=debugEditor(t)
  state.name.value='独立调试';state.expectedStatus.value=404;state.request.value.pathParams.id='999'
  await state.send()
  assert.equal(calls.length,1);assert.equal(calls[0][0],5);assert.equal(calls[0][1],3)
  assert.equal(calls[0][2].step.expected_status,404);assert.equal(calls[0][2].step.path_params.id,'999')
  assert.equal(props.step.expected_status,200);assert.equal(events.some(([name])=>name==='apply'),false)
  assert.equal(state.result.value.response_detail.body.id,42)
})

test('JSONPath verification uses the previous response ticket and never resends the HTTP request',async t=>{
  const {state,calls,props}=debugEditor(t)
  await state.send();state.extracts.value='{"order_id":"$.id"}'
  await state.verifyExtraction()
  assert.equal(calls.length,2);assert.equal(calls[1][0],'extract')
  assert.equal(calls[1][3].response_id,'b'.repeat(32));assert.deepEqual(props.variables,{order_id:42})
  state.url.value='/orders/changed'
  await state.verifyExtraction();assert.equal(calls.length,2);assert.ok(state.debugError.value.includes('已修改'))
})

test('missing environment, invalid extraction JSON and busy clicks cannot send duplicate requests',async t=>{
  let finish
  const {state,props,calls}=debugEditor(t,{debugScenarioStep:(...args)=>{calls.push(args);return new Promise(resolve=>finish=resolve)}})
  props.envId='';await state.send();assert.equal(calls.length,0)
  props.envId=3;const pending=state.send();await state.send();assert.equal(calls.length,1)
  finish({step_id:props.step.step_id,session_id:'a'.repeat(32),response_id:'b'.repeat(32),variables:{}});await pending
  state.extracts.value='broken';await state.verifyExtraction();assert.equal(calls.length,1);assert.ok(state.debugError.value.includes('JSON'))
})

test('closed editor ignores a late response and clearing transient variables never applies a draft',async t=>{
  let finish
  const editor=debugEditor(t,{debugScenarioStep:()=>new Promise(resolve=>finish=resolve)})
  const pending=editor.state.send();editor.dispose();finish({session_id:'a'.repeat(32),variables:{order_id:42}});await pending
  assert.equal(editor.events.length,0)
  const next=debugEditor(t);await next.state.send();next.state.clearDebug()
  assert.equal(next.state.result.value,null);assert.equal(next.events.at(-1)[0],'reset-debug')
  assert.equal(next.events.some(([name])=>name==='apply'),false)
})

test('debug variables and modal are cleared synchronously when the environment or account changes',async t=>{
  const auth=Vue.reactive({token:'alice',currentProjectId:1})
  const {state}=await page(t,{useAuthStore:()=>auth})
  state.editStep(state.chain.value[0],true)
  state.rememberDebug({step_id:state.chain.value[0].step_id,session_id:'a'.repeat(32),variables:{order_id:42}})
  state.selectedEnv.value=4
  assert.equal(state.debugSession.value,'');assert.equal(state.editingStep.value,null)
  state.rememberDebug({step_id:'x',session_id:'b'.repeat(32),variables:{order_id:9}})
  auth.token='bob';assert.deepEqual(state.debugVariables.value,{})
})
