import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import * as Vue from 'vue'
import { renderToString } from '@vue/server-renderer'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import * as rules from '../src/utils/assertionRules.js'
import { newPerfStep, buildPerfPlan } from '../src/utils/perf-plan.js'
const { assertionRows, serializeAssertions, matchingAssertionResult, newAssertionRow } = rules

function component(file) {
  const d=parse(readFileSync(new URL(file,import.meta.url),'utf8')).descriptor
  const script=compileScript(d,{id:file}),names=Object.keys(script.imports)
  const code=script.content.replace(/^import[\s\S]*?\bfrom\s*['"][^'"]+['"];?/gm,'').replace('export default','return')
  const options=Function(...names,code)(...names.map(name=>rules[name]??Vue[name]))
  const template=compileTemplate({source:d.template.content,id:file,compilerOptions:{bindingMetadata:script.bindings}})
  assert.deepEqual(template.errors,[])
  const render=template.code.replace(/import\s*\{([^}]+)\}\s*from\s*['"]vue['"];?/g,(_,items)=>`const {${items.replace(/\bas\b/g,':')}}=Vue;`).replace('export function render','return function render')
  options.render=Function('Vue',render)(Vue)
  return options
}
const Editor=component('../src/components/AssertionEditor.vue'),Results=component('../src/components/AssertionResults.vue')
const html=(component,props)=>renderToString(Vue.createSSRApp(component,props))
const samples=[{type:'json_eq',path:'$.id',expected:42},{type:'json_contains',path:'$.items',expected:{id:42}},
  {type:'json_gt',path:'$.id',expected:0},{type:'json_lt',path:'$.price',expected:100},
  {type:'header_eq',path:'Content-Type',expected:'application/json'},
  {type:'header_contains',path:'Content-Type',expected:'json'}, {type:'response_time_lt',expected:1000},
  {type:'json_schema',expected:{type:'object',required:['id']}},{type:'db_eq',sql:'SELECT COUNT(*) FROM orders',expected:1}]

test('all existing assertion types and scalar or structured expected values roundtrip without losing fields',()=>{
  assert.deepEqual(serializeAssertions(assertionRows(samples)),samples)
  for(const value of ['42',42,true,false,null,'',[],{id:0},'${order_id}']) {
    const source=[{type:'json_eq',path:'data.id',expected:value,description:'旧字段保留',target:'legacy-metadata'}]
    const rows=assertionRows(source)
    assert.deepEqual(serializeAssertions(rows),source)
    rows[0].path='$.changed';assert.equal(source[0].path,'data.id')
  }
  const legacy=[{type:'custom_type',expected:42,options:{nested:true}}]
  assert.equal(assertionRows(legacy)[0].target,'custom')
  assert.deepEqual(serializeAssertions(assertionRows(legacy)),legacy)
  for(const schema of [true,false]) assert.deepEqual(serializeAssertions(assertionRows([{type:'json_schema',expected:schema}])),[{type:'json_schema',expected:schema}])
})

test('typed input distinguishes strings from numbers and preserves false, null and empty strings',()=>{
  const row={...newAssertionRow('json'),path:'$.id',expectedText:'42'}
  assert.equal(serializeAssertions([row])[0].expected,'42')
  row.expectedType='number';assert.equal(serializeAssertions([row])[0].expected,42)
  row.expectedText='';assert.throws(()=>serializeAssertions([row]),/有效数字/)
  row.expectedText='Infinity';assert.throws(()=>serializeAssertions([row]),/有效数字/)
  row.expectedType='boolean';row.expectedText='false';assert.equal(serializeAssertions([row])[0].expected,false)
  row.expectedType='null';assert.equal(serializeAssertions([row])[0].expected,null)
  row.expectedType='string';row.expectedText='';assert.equal(serializeAssertions([row])[0].expected,'')
})

test('incomplete fields, invalid JSON and incompatible load assertions block save while blank rows clear',()=>{
  assert.equal(serializeAssertions([newAssertionRow()]),null)
  assert.deepEqual(serializeAssertions([],{empty:[]}),[])
  assert.throws(()=>serializeAssertions([newAssertionRow('json')]),/JSONPath/)
  assert.throws(()=>serializeAssertions([{...newAssertionRow('schema'),expectedText:'broken'}]),/JSON/)
  assert.throws(()=>serializeAssertions([{...newAssertionRow('schema'),expectedText:'[]'}]),/Schema/)
  assert.throws(()=>serializeAssertions([{type:'json_eq',path:'$.id'}]),/期望值类型/)
  assert.throws(()=>serializeAssertions([samples.at(-1)],{allowDatabase:false}),/不支持数据库/)
  assert.throws(()=>serializeAssertions([{type:'response_time_lt',expected:0}],{strict:true}),/大于 0/)
  assert.throws(()=>serializeAssertions([{type:'custom_type',expected:1}],{strict:true}),/不支持/)
})

test('editing one assertion, changing its value type and deleting rows leaves saved configuration untouched',t=>{
  const props=Vue.reactive({modelValue:assertionRows(samples.slice(0,1)),idPrefix:'test',allowDatabase:true,strict:false,results:[],resultRules:[],resultsEnabled:true})
  const scope=Vue.effectScope();t.after(()=>scope.stop())
  const state=scope.run(()=>Editor.setup(props,{expose(){},emit(_,value){props.modelValue=value}}))
  state.update(0,'expectedText','99');assert.equal(serializeAssertions(props.modelValue)[0].expected,99)
  state.update(0,'expectedType','boolean');state.update(0,'expectedText','false');assert.equal(serializeAssertions(props.modelValue)[0].expected,false)
  state.add();state.update(1,'path','$.active');state.update(1,'expectedType','null')
  assert.deepEqual(serializeAssertions(props.modelValue)[1],{type:'json_eq',path:'$.active',expected:null})
  assert.equal(samples[0].expected,42)
  state.remove(1);state.remove(0);assert.equal(serializeAssertions(props.modelValue),null)
  state.update(0,'target','time');state.update(0,'expectedText','500')
  assert.deepEqual(serializeAssertions(props.modelValue),[{type:'response_time_lt',expected:500}])
})

test('result matching requires the exact executed rule and position rather than only its type',()=>{
  const executed=[{type:'json_eq',path:'$.id',expected:42},{type:'json_eq',path:'$.other',expected:0}]
  const results=executed.map(rule=>({type:rule.type,actual:rule.expected,expected:rule.expected,passed:true}))
  const rows=assertionRows(executed)
  assert.equal(matchingAssertionResult(rows[1],1,executed,results).actual,0)
  assert.equal(matchingAssertionResult(rows[1],0,executed,results),null)
  rows[0].expectedText='0';assert.equal(matchingAssertionResult(rows[0],0,executed,results),null)
  assert.equal(matchingAssertionResult(rows[1],1,[],results),null)
})

test('the real editor and result table expose human labels and safely render falsy or HTML values',async()=>{
  const expected=[{type:'json_eq',path:'$.active',expected:false}]
  const result=[{type:'json_eq',expected:false,actual:false,passed:true}]
  const output=await html(Editor,{idPrefix:'test',modelValue:assertionRows(expected),results:result,resultRules:expected})
  for(const word of ['断言对象','判断条件','期望值','实际值 / 结果','false','通过']) assert.ok(output.includes(word),word)
  const stale=await html(Editor,{idPrefix:'test',modelValue:assertionRows([{type:'json_eq',path:'$.other',expected:false}]),results:result,resultRules:expected})
  assert.ok(stale.includes('待执行'));assert.ok(!stale.includes('class="passed"'))
  const restricted=await html(Editor,{idPrefix:'test',allowDatabase:false})
  assert.ok(!restricted.includes('value="database"'))
  const readonly=await html(Results,{results:[{type:'json_eq',expected:null,actual:0,passed:false},{type:'header_contains',expected:'<script>',actual:'<img onerror=x>',passed:false}]})
  assert.ok(readonly.includes('null'));assert.ok(readonly.includes('>0<'));assert.ok(readonly.includes('&lt;img'));assert.ok(!readonly.includes('<img'));assert.ok(!readonly.includes('<input'))
  const boolSchema=await html(Editor,{idPrefix:'test',modelValue:assertionRows([{type:'json_schema',expected:false}])})
  assert.ok(boolSchema.includes('JSON Schema'));assert.ok(boolSchema.includes('false'))
})

test('load plan imports structured assertions and serializes the edited table to the existing wire format',()=>{
  const form={mode:'single',variables:'{}',datasets:'[]',stop_on_failure:true,wait_seconds:1,timeout_seconds:30}
  const step=newPerfStep({assertions:samples.slice(0,-1)})
  assert.deepEqual(buildPerfPlan(form,[step]).steps[0].assertions,samples.slice(0,-1))
  step.assertions[0].expectedText='99';assert.equal(buildPerfPlan(form,[step]).steps[0].assertions[0].expected,99)
  step.assertions=[];assert.deepEqual(buildPerfPlan(form,[step]).steps[0].assertions,[])
})
