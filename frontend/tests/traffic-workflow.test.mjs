import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import * as Vue from 'vue'
import { parse, compileScript } from '@vue/compiler-sfc'
const descriptor = parse(readFileSync(new URL('../src/views/Traffic.vue',import.meta.url),'utf8')).descriptor
const script = compileScript(descriptor,{id:'traffic-tests'}).content.replace(/import\s*\{([^}]+)\}\s*from\s*['"]vue['"];?/g,(_,names)=>`const {${names.replace(/\bas\b/g,':')}}=Vue;`).replace(/^import .+$/gm,'').replace('export default','return')
const tick=()=>new Promise(resolve=>setImmediate(resolve))
const record={id:1,method:'GET',path:'/orders/123',interface_name:'查询订单',source:'debug',request_headers:{Authorization:'***'},request_params:{page:1},request_body:null}
function view(t,overrides={}){
 const auth=Vue.reactive({currentProjectId:1}),calls=[],cleanups=[]
 const options=Function('Vue','useAuthStore','useFeedback','listRecords','getRecord','replayRecord','captureState','startCapture','stopCapture','listEnvironments','Modal','EnvironmentSelect','setInterval','clearInterval',script)(
 {...Vue,onBeforeUnmount:fn=>cleanups.push(fn)},()=>auth,()=>({showMessage(){}}),
 async params=>{calls.push(['list',params]);return [record]},async id=>record,
 async(id,payload)=>{calls.push(['replay',id,payload]);return overrides.replay?overrides.replay(id,payload):{diff:{same:true,diffs:[]}}},
 overrides.state|| (async()=>({active:false,capture_id:'cap',count:1})),
 overrides.start || (async()=>({active:true,capture_id:'new',count:0})),async()=>({active:false,capture_id:'cap',count:1}),
 async()=>[{id:1,name:'目标环境',base_url:'http://target.invalid'}],null,null,()=>0,()=>{})
 const scope=Vue.effectScope(),state=scope.run(()=>options.setup({}, {expose(){}}))
 t.after(()=>{cleanups.forEach(fn=>fn());scope.stop()})
 return {state,auth,calls}
}
test('recording controls guard duplicate clicks and remain scoped to the selected project',async t=>{
 let resolve
 const {state,auth,calls}=view(t,{start:()=>new Promise(r=>resolve=r)});await tick()
 const pending=state.toggleCapture();await state.toggleCapture();auth.currentProjectId=2;await tick();resolve({active:true,capture_id:'old'});await pending
 assert.notEqual(state.capture.value?.capture_id,'old');assert.equal(state.busy.value,false)
})
test('replay waits for explicit environment selection and never sends when opening details',async t=>{
 const {state,calls}=view(t);await tick();await state.openRecord(record,'replay')
 assert.equal(calls.filter(x=>x[0]==='replay').length,0)
 await state.sendReplay();assert.match(state.modalError.value,/环境/)
 state.envId.value=1;state.headers.value='{"Authorization":"Bearer ${token}"}'
 state.ignored.value='trace_id，request_id';await state.sendReplay()
 const sent=calls.find(x=>x[0]==='replay')[2]
 assert.equal(sent.env_id,1);assert.equal(sent.headers.Authorization,'Bearer ${token}');assert.equal(sent.body,null)
 assert.deepEqual(sent.field_rules,{trace_id:'ignore',request_id:'ignore'})
})
test('invalid JSON and invalid header values retain the draft and do not send',async t=>{
 const {state,calls}=view(t);await tick();await state.openRecord(record,'replay');state.envId.value=1
 state.body.value='{';await state.sendReplay();assert.match(state.modalError.value,/合法 JSON/)
 assert.equal(state.body.value,'{');state.body.value='null';state.headers.value='{"x":1}'
 await state.sendReplay();assert.match(state.modalError.value,/字符串/)
 assert.equal(calls.filter(x=>x[0]==='replay').length,0)
})
test('late replay result cannot appear in a different project and duplicate sends are blocked',async t=>{
 let resolve
 const {state,auth,calls}=view(t,{replay:()=>new Promise(r=>resolve=r)});await tick();await state.openRecord(record,'replay');state.envId.value=1;state.headers.value='{}'
 const pending=state.sendReplay();await state.sendReplay();assert.equal(calls.filter(x=>x[0]==='replay').length,1)
 auth.currentProjectId=2;await tick();resolve({diff:{same:true}});await pending
 assert.equal(state.result.value,null);assert.equal(state.modal.value,'');assert.equal(state.headers.value,'')
})
test('latest load wins when switching projects and pagination uses server offsets',async t=>{
 let resolve,count=0
 const {state,auth,calls}=view(t,{state:()=>++count===1?new Promise(r=>resolve=r):Promise.resolve({active:false,capture_id:'new',count:0})})
 auth.currentProjectId=2;await tick();resolve({active:true,capture_id:'old'});await tick()
 assert.equal(state.capture.value.capture_id,'new')
 state.changePage(1);await tick();assert.equal(calls.at(-1)[1].offset,20)
})
test('initial session without captures stays empty until user starts or chooses project history',async t=>{
 const {state,calls}=view(t,{state:async()=>({active:false,capture_id:null,count:0})});await tick()
 assert.equal(calls.length,0);state.changeScope('all');await tick()
 assert.equal(calls[0][0],'list');assert.equal(calls[0][1].capture_id,undefined)
})
