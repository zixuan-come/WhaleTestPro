import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import * as Vue from 'vue'
import { parse, compileScript } from '@vue/compiler-sfc'
import { suiteCatalog, selectedSuiteContent, filterSuiteContent } from '../src/utils/suiteSelection.js'

const source = parse(readFileSync(new URL('../src/components/SuiteContentPicker.vue', import.meta.url), 'utf8')).descriptor
const compiled = compileScript(source, { id:'suite-picker-contract' })
const code = compiled.content.replace(/^import[^\n]*\n/gm, '').replace('export default', 'return')
const cases = Array.from({ length:55 }, (_, i) => ({ id:i+1, name:`用例${i+1}`, interface_id:i%2 ? 20 : 10 }))
const scenarios = [{ id:1, name:'下单主流程', case_ids:[1,2] }, { id:2, name:'取消流程', case_ids:[3] }]
const interfaces = [{ id:10, name:'订单查询' }, { id:20, name:'订单创建' }]
const tick = () => new Promise(resolve => setImmediate(resolve))

function picker(t, overrides={}, selection={ scenario_ids:[], case_ids:[] }) {
  const callbacks=[], events=[], auth=Vue.reactive({ username:'picker-user', token:'synthetic', currentProjectId:1 })
  const props=Vue.reactive({ modelValue:structuredClone(selection), disabled:false })
  const mocks={ ...Vue, onMounted() {}, onBeforeUnmount(fn) { callbacks.push(fn) }, useAuthStore:()=>auth,
    listScenarios:async()=>scenarios, listCases:async()=>cases, listInterfaces:async()=>interfaces,
    suiteCatalog, selectedSuiteContent, filterSuiteContent, HiddenScrollArea:{}, SuiteFilterSelect:{}, ...overrides }
  const component=Function(...Object.keys(compiled.imports),code)(...Object.keys(compiled.imports).map(name=>mocks[name]))
  const scope=Vue.effectScope(), state=scope.run(()=>component.setup(props,{ expose(){},emit(name,value){ events.push([name,value]);if(name==='update:modelValue')props.modelValue=value } }))
  t.after(()=>{callbacks.forEach(fn=>fn());scope.stop()})
  return {state,props,auth,events,callbacks}
}

test('search covers all project content before pagination and includes parent interface names',async t=>{
  const {state}=picker(t);await state.load();state.setKind('case')
  assert.equal(state.pages.value,3);assert.equal(state.visible.value.length,20)
  state.query.value='用例55';assert.deepEqual(state.visible.value.map(item=>item.id),[55])
  state.query.value='订单创建';assert.equal(state.filtered.value.length,27)
  state.interfaceId.value='10';assert.equal(state.filtered.value.length,0)
})

test('checkbox and full-page selections persist across pages and filters',async t=>{
  const {state,props}=picker(t);await state.load();state.setKind('case');state.togglePage()
  state.changePage(2);state.togglePage();assert.equal(props.modelValue.case_ids.length,40)
  state.togglePage();assert.deepEqual(props.modelValue.case_ids,Array.from({length:20},(_,i)=>i+1))
  state.query.value='用例55';state.toggleItem(state.visible.value[0])
  assert.equal(props.modelValue.case_ids.length,21)
  state.query.value='';state.changePage(3);assert.ok(props.modelValue.case_ids.includes(55))
})

test('scenario coverage is marked without silently deleting explicit legacy selections',async t=>{
  const {state,props}=picker(t,{}, {scenario_ids:[],case_ids:[1]});await state.load()
  state.toggleItem(state.visible.value[0]);state.setKind('case')
  assert.equal(state.chosen.value.cases[0].included,true)
  state.toggleItem(state.visible.value.find(item=>item.id===2));assert.deepEqual(props.modelValue.case_ids,[1])
  state.toggleItem(state.visible.value.find(item=>item.id===1));assert.deepEqual(props.modelValue.case_ids,[])
})

test('ordered scenarios and unresolved legacy IDs remain explicit',async t=>{
  const {state,props}=picker(t,{}, {scenario_ids:[2,1,999],case_ids:[4,998]});await state.load()
  assert.equal(state.chosen.value.scenarios[2].missing,true)
  state.moveScenario(1,-1);assert.deepEqual(props.modelValue.scenario_ids,[1,2,999])
  assert.deepEqual(props.modelValue.case_ids,[4,998])
})

test('a failed catalog load preserves the draft and prevents ready until retry succeeds',async t=>{
  let fail=true
  const {state,props,events}=picker(t,{listCases:async()=>{if(fail)throw Error('load failed');return cases}}, {scenario_ids:[1],case_ids:[4]})
  await state.load();assert.match(state.error.value,/load failed/)
  assert.equal(events.at(-1)[1],false);assert.deepEqual(props.modelValue.case_ids,[4])
  fail=false;await state.load();assert.equal(events.at(-1)[1],true)
})

test('a late response from another project or an unmounted picker cannot restore a catalog',async t=>{
  let resolve, first=true
  const old=new Promise(r=>resolve=r)
  const {state,auth,callbacks}=picker(t,{listScenarios:()=>{if(first){first=false;return old}return Promise.resolve([{id:9,name:'新项目场景',case_ids:[]}])}})
  const pending=state.load();auth.currentProjectId=2;await tick()
  resolve(scenarios);await pending
  assert.deepEqual(state.catalog.value.scenarios.map(item=>item.name),['新项目场景'])
  callbacks.forEach(fn=>fn())
})

test('selection limits reject the whole over-limit operation and disabled pickers cannot mutate',async t=>{
  const {state,props}=picker(t,{}, {scenario_ids:[],case_ids:Array.from({length:100},(_,i)=>i+100)})
  await state.load();state.setKind('case');state.togglePage();assert.equal(props.modelValue.case_ids.length,100)
  assert.match(state.notice.value,/100/)
  props.disabled=true;state.clear();state.toggleItem(state.visible.value[0]);assert.equal(props.modelValue.case_ids.length,100)
})
