import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parse, compileScript } from '@vue/compiler-sfc'
import * as Vue from 'vue'

const desc=parse(readFileSync(new URL('../src/components/ProjectNotifications.vue',import.meta.url),'utf8')).descriptor
const script=compileScript(desc,{id:'project-notification-test'}).content
 .replace(/import\s*\{([^}]+)\}\s*from\s*['"]vue['"];?/g,(_,names)=>`const {${names.replace(/\bas\b/g,':')}}=Vue;`)
 .replace(/^import .+$/gm,'').replace('export default','return')
const tick=()=>new Promise(resolve=>setImmediate(resolve))
const configured={enabled:true,configured:true,signing_configured:true,can_manage:true}
function view(t,overrides={}){
 const auth=Vue.reactive({username:'owner',token:'fixture',currentTeamRole:'owner'}),props=Vue.reactive({project:{id:1,name:'订单项目'}}),calls=[],cleanups=[]
 const options=Function('Vue','useAuthStore','getProjectNotifications','saveProjectNotifications','testProjectNotifications','showMessage','Modal',script)(
  {...Vue,onBeforeUnmount:fn=>cleanups.push(fn)},()=>auth,overrides.get|| (async()=>configured),
  async(id,payload)=>{calls.push(['save',id,payload]);return overrides.save?overrides.save(id,payload):configured},
  async id=>{calls.push(['test',id]);if(overrides.test)return overrides.test(id)},()=>{},null)
 const scope=Vue.effectScope(),state=scope.run(()=>options.setup(props,{expose(){},emit(){}}))
 t.after(()=>{cleanups.forEach(fn=>fn());scope.stop()})
 return {state,props,auth,calls}
}
test('saved credentials stay blank and tests require saving any edits first',async t=>{
 const {state,calls}=view(t);await tick()
 assert.equal(state.form.webhook,'');assert.equal(state.form.secret,'');assert.equal(state.dirty.value,false)
 await state.sendTest();assert.deepEqual(calls,[['test',1]])
 state.form.webhook='https://open.feishu.cn/open-apis/bot/v2/hook/fixture'
 await state.sendTest();assert.equal(calls.length,1)
 state.form.secret='new-secret';await state.save()
 assert.equal(calls[1][0],'save');assert.equal(calls[1][2].signing_secret,'new-secret')
 assert.equal(state.form.webhook,'');assert.equal(state.form.secret,'');assert.equal(state.dirty.value,false)
})
test('failure retains input and members cannot invoke save or test through handlers',async t=>{
 const {state,auth,calls}=view(t,{save:async()=>{throw Error('保存失败')}});await tick()
 state.form.webhook='new-value';await state.save()
 assert.equal(state.form.webhook,'new-value');assert.equal(state.error.value,'保存失败')
 auth.currentTeamRole='member';await tick();state.form.webhook='forbidden'
 await state.save();await state.sendTest();assert.equal(calls.length,1)
})
test('late save completion cannot clear a different project draft',async t=>{
 let finish
 const {state,props}=view(t,{save:()=>new Promise(resolve=>finish=resolve)});await tick()
 state.form.webhook='old';const pending=state.save()
 props.project={id:2,name:'新项目'};await tick();state.form.webhook='new'
 finish(configured);await pending
 assert.equal(state.form.webhook,'new');assert.equal(state.saving.value,false)
})
test('duplicate test clicks make one request and failure message stays visible',async t=>{
 let finish
 const {state,calls}=view(t,{test:()=>new Promise((_,reject)=>finish=reject)});await tick()
 const pending=state.sendTest();await state.sendTest();assert.equal(calls.length,1)
 finish(Error('关键词校验失败'));await pending
 assert.equal(state.error.value,'关键词校验失败');assert.equal(state.testing.value,false)
})
