import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import * as Vue from 'vue'
import { renderToString } from '@vue/server-renderer'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import * as extraction from '../src/utils/extractRules.js'
import { newPerfStep, buildPerfPlan } from '../src/utils/perf-plan.js'
const { extractRuleRows, serializeExtractRules, SCENARIO_EXTRACT_OPTIONS, PERF_EXTRACT_OPTIONS } = extraction

function component(file) {
  const d = parse(readFileSync(new URL(file, import.meta.url), 'utf8')).descriptor
  const script = compileScript(d, { id: file })
  const names = Object.keys(script.imports)
  const code = script.content.replace(/^import[\s\S]*?\bfrom\s*['"][^'"]+['"];?/gm, '').replace('export default', 'return')
  const options = Function(...names, code)(...names.map(name => extraction[name] ?? Vue[name]))
  const template = compileTemplate({ source: d.template.content, id: file, compilerOptions: { bindingMetadata: script.bindings } })
  assert.deepEqual(template.errors, [])
  const render = template.code.replace(/import\s*\{([^}]+)\}\s*from\s*['"]vue['"];?/g,
    (_, items) => `const {${items.replace(/\bas\b/g, ':')}} = Vue;`).replace('export function render', 'return function render')
  options.render = Function('Vue', render)(Vue)
  return options
}
const Editor = component('../src/components/ExtractRulesEditor.vue')
const Variables = component('../src/components/ExtractedVariables.vue')
const html = (options, props) => renderToString(Vue.createSSRApp(options, props))

test('existing rule mappings roundtrip without changing legacy JSONPath or mutating the source', () => {
  for (const source of [null, {}, { order_id: '$.id', token: 'data.token' }, '{"order_id":"$.id"}']) {
    const rows = extractRuleRows(source)
    assert.deepEqual(serializeExtractRules(rows), source == null || JSON.stringify(source) === '{}' ? null : typeof source === 'string' ? JSON.parse(source) : source)
  }
  const source = { order_id: '$.id' }, rows = extractRuleRows(source)
  rows[0].path = '$.data.id'
  assert.equal(source.order_id, '$.id')
  assert.deepEqual(serializeExtractRules([{name:'',path:''}]), null)
  assert.deepEqual(serializeExtractRules([], {empty:{}}), {})
})

test('incomplete rows, duplicates, malformed legacy rules and reserved names cannot silently overwrite values', () => {
  assert.throws(() => serializeExtractRules([{name:'id',path:''}]), /同时填写/)
  assert.throws(() => serializeExtractRules([{name:'',path:'$.id'}]), /同时填写/)
  assert.throws(() => serializeExtractRules([{name:'id',path:'$.id'},{name:' id ',path:'$.other'}]), /重复/)
  assert.throws(() => serializeExtractRules({id:3}), /文本/)
  assert.throws(() => serializeExtractRules('{broken'), /JSON/)
  assert.throws(() => serializeExtractRules({base_url:'$.id'}, SCENARIO_EXTRACT_OPTIONS), /保留变量/)
  assert.throws(() => serializeExtractRules({_vu_id:'$.id'}, PERF_EXTRACT_OPTIONS), /保留变量/)
  assert.throws(() => serializeExtractRules({id:'x'.repeat(501)}, SCENARIO_EXTRACT_OPTIONS), /500/)
  assert.throws(() => serializeExtractRules(Array.from({length:51},(_,i)=>({name:`v${i}`,path:'$.id'})), PERF_EXTRACT_OPTIONS), /50/)
  assert.deepEqual(serializeExtractRules({订单号:'$.id'}), {订单号:'$.id'})
  const prototypeName = serializeExtractRules([{name:'__proto__',path:'$.id'}])
  assert.equal(Object.hasOwn(prototypeName, '__proto__'), true)
  assert.equal(prototypeName.__proto__, '$.id')
})

test('the shared editor adds, edits and removes rules without mutating saved mappings', t => {
  const source = {id:'$.id'}
  const props = Vue.reactive({modelValue:extractRuleRows(source),idPrefix:'test',rulesOptions:{},results:[],resultsEnabled:true})
  const scope = Vue.effectScope(); t.after(()=>scope.stop())
  const state = scope.run(()=>Editor.setup(props,{expose(){},emit(name,value){props.modelValue=value}}))
  state.update(0,'path','$.data.id');state.add();state.update(1,'name','token');state.update(1,'path','$.token')
  assert.deepEqual(serializeExtractRules(props.modelValue),{id:'$.data.id',token:'$.token'})
  assert.deepEqual(source,{id:'$.id'})
  state.remove(0);state.remove(0)
  assert.deepEqual(serializeExtractRules(props.modelValue),null)
  assert.deepEqual(state.rows.value,[{name:'',path:''}])
  state.update(0,'name','incomplete');assert.match(state.validation.value,/同时填写/)
})

test('results only belong to the same name, expression and current response', t => {
  const props=Vue.reactive({modelValue:[{name:'id',path:'$.id'}],idPrefix:'test',rulesOptions:{},results:[{name:'id',path:'$.id',passed:true,value:0}],resultsEnabled:true})
  const scope=Vue.effectScope();t.after(()=>scope.stop())
  const state=scope.run(()=>Editor.setup(props,{expose(){},emit(){}}))
  assert.equal(state.resultFor(props.modelValue[0]).value,0)
  assert.equal(state.resultFor({name:'other',path:'$.id'}),null)
  assert.equal(state.resultFor({name:'id',path:'$.data.id'}),null)
  props.resultsEnabled=false;assert.equal(state.resultFor(props.modelValue[0]),null)
})

test('table results preserve falsy values, show failures and escape response content', async () => {
  const values=[0,false,null,'',[],{id:42},'<script>alert(1)</script>']
  const results=values.map((value,index)=>({name:`v${index}`,path:`$.v${index}`,passed:true,value}))
  const output=await html(Editor,{idPrefix:'test',modelValue:results.map(({name,path})=>({name,path})),results})
  for(const text of ['变量名','提取表达式','提取结果','false','null','[]','42','&lt;script&gt;']) assert.ok(output.includes(text),text)
  assert.ok(!output.includes('<script>'))
  assert.ok((await html(Editor,{idPrefix:'test',modelValue:{id:'$.id'},results:[{name:'id',path:'$.id',passed:false,error:'未找到匹配值'}]})).includes('未找到匹配值'))
  assert.ok((await html(Editor,{idPrefix:'test',modelValue:{id:'$.id'},resultPlaceholder:'运行时提取'})).includes('运行时提取'))
  const readonly=await html(Variables,{variables:{id:0,ok:false,empty:null,list:[],html:'<img onerror=alert(1)>'}})
  assert.ok(readonly.includes('false'));assert.ok(readonly.includes('null'));assert.ok(readonly.includes('&lt;img'))
  assert.ok(!readonly.includes('<input'));assert.ok(!readonly.includes('提取表达式'))
})

test('performance configuration saves mappings from rows and can explicitly clear imported extraction rules', () => {
  const form={mode:'single',variables:'{}',datasets:'[]',stop_on_failure:true,wait_seconds:1,timeout_seconds:30}
  const step=newPerfStep({extract_rules:{id:'$.id'}})
  assert.deepEqual(buildPerfPlan(form,[step]).steps[0].extract_rules,{id:'$.id'})
  step.extract_rules=[{name:'id',path:'$.data.id'}]
  assert.deepEqual(buildPerfPlan(form,[step]).steps[0].extract_rules,{id:'$.data.id'})
  step.extract_rules=[];assert.deepEqual(buildPerfPlan(form,[step]).steps[0].extract_rules,{})
  step.extract_rules=[{name:'id',path:''}];assert.throws(()=>buildPerfPlan(form,[step]),/第 1 步.*同时填写/)
})
