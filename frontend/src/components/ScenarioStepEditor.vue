<script setup>
import { ref, computed, watch, nextTick, onBeforeUnmount } from 'vue'
import Modal from './Modal.vue'
import RequestEditor from './RequestEditor.vue'
import CaseResponse from './CaseResponse.vue'
import { debugScenarioStep, validateScenarioExtraction } from '../api/scenario'
import { cloneRequest, requestDraft, serializeRequest } from '../utils/requestConfig'

const props = defineProps({ step: { type: Object, required: true }, busy: Boolean, scenarioId:Number,
  envId:[String,Number], environmentName:String, debugMode:Boolean, sessionId:String,
  variables:{type:Object,default:()=>({})}, debugResult:Object })
const emit = defineEmits(['apply', 'close', 'reapply', 'debug', 'reset-debug'])
const result = ref(props.debugResult || null)
const debugVisible = ref(props.debugMode || Boolean(props.debugResult))
const sending = ref(false), verifying = ref(false), debugError = ref(''), copied = ref(false)
const manualVariables = ref(Object.create(null))
const debugPanel = ref(null), extractionPanel = ref(null)
const locked = computed(() => props.busy || sending.value || verifying.value)
let requestVersion = 0
onBeforeUnmount(() => { requestVersion++ })
watch(() => props.debugResult, value => { result.value = value || null })
const name = ref(props.step.name)
const method = ref(props.step.method || 'GET')
const url = ref(props.step.url || '')
const expectedStatus = ref(props.step.expected_status)
const request = ref(requestDraft(props.step))
const originalRequest = cloneRequest(request.value)
const assertions = ref(props.step.assertions == null ? '' : JSON.stringify(props.step.assertions, null, 2))
const extracts = ref(props.step.extract_rules == null ? '' : JSON.stringify(props.step.extract_rules, null, 2))
const advanced = ref(false)
const error = ref('')
const editor = ref(null)
const unsupported = Boolean(props.step.setup_sql?.length || props.step.teardown_sql?.length || props.step.datasets?.length || props.step.retries > 0)

function json(text, label, array) {
  if (!text.trim()) return null
  let value
  try { value = JSON.parse(text) } catch { throw Error(`${label}不是合法 JSON`) }
  if (!value || (array ? !Array.isArray(value) : typeof value !== 'object' || Array.isArray(value))) throw Error(`${label}必须是 JSON ${array ? '数组' : '对象'}`)
  if (array && value.some(item => !item || Array.isArray(item) || typeof item !== 'object')) throw Error('每条断言必须是 JSON 对象')
  if (!array && Object.values(value).some(item => typeof item !== 'string')) throw Error('提取规则的值必须是 JSONPath 文本')
  return value
}

function buildStep() {
  error.value = ''
  if (!name.value.trim()) { error.value = '请填写步骤名称'; return null }
  if (!url.value.trim().startsWith('/') || url.value.trim().length > 500) { error.value = '请填写不超过 500 字符、以 / 开头的请求路径'; return }
  if (!Number.isInteger(Number(expectedStatus.value)) || expectedStatus.value < 100 || expectedStatus.value > 599) { error.value = '期望状态码必须是 100～599 的整数'; return }
  try {
    const fields = serializeRequest(request.value, url.value)
    // Editing a name/status must not coerce untouched Query JSON values into
    // text or turn explicit nulls into empty objects.
    for (const [draftKey, savedKey] of [['headers','headers'], ['params','params'], ['pathParams','path_params']]) {
      if (url.value.trim() === props.step.url && JSON.stringify(request.value[draftKey]) === JSON.stringify(originalRequest[draftKey])) {
        fields[savedKey] = cloneRequest(props.step[savedKey] ?? null)
      }
    }
    if (request.value.bodyType === originalRequest.bodyType && request.value.body === originalRequest.body) fields.body = cloneRequest(props.step.body ?? null)
    let rules, checks
    try { rules = json(extracts.value, '提取规则', false); checks = json(assertions.value, '断言', true) }
    catch (e) { advanced.value = true; throw e }
    return { ...cloneRequest(props.step), ...fields, name:name.value.trim(), method:method.value,
      url:url.value.trim(), expected_status:Number(expectedStatus.value), assertions:checks, extract_rules:rules }
  } catch (e) { error.value = e.message; if (e.tab) editor.value?.focusError(e); return null }
}
function apply() {
  if (locked.value || props.step.missing_reason) return
  const step = buildStep()
  if (step) emit('apply', step)
}
function requestKey() {
  return JSON.stringify([method.value, url.value, request.value, String(props.envId || '')])
}
const staleResponse = computed(() => result.value && result.value.draft_key !== requestKey())
async function send() {
  if (locked.value || props.step.missing_reason) return
  debugVisible.value = true; debugError.value = ''; copied.value = false
  if (!props.envId) { debugError.value = '请先在场景顶部选择执行环境'; return }
  const step = buildStep()
  if (!step) return
  const version = ++requestVersion, key = requestKey()
  sending.value = true
  try {
    const data = await debugScenarioStep(props.scenarioId, props.envId, {
      step, ...(props.sessionId ? {session_id:props.sessionId} : {}), variables:cloneRequest(manualVariables.value),
    })
    if (version !== requestVersion) return
    result.value = { ...data, draft_key:key }
    emit('debug', result.value)
    await nextTick()
    debugPanel.value?.scrollIntoView({ block:'start', behavior:'smooth' })
  } catch (e) { if (version === requestVersion) debugError.value = e.message || '发送失败，请检查网络后重试' }
  finally { if (version === requestVersion) sending.value = false }
}
async function verifyExtraction() {
  if (locked.value || !result.value?.response_id) return
  debugError.value = ''
  if (staleResponse.value) { debugError.value = '请求配置已修改，请重新发送后验证提取'; return }
  let rules
  try { rules = json(extracts.value, '提取规则', false) || {} }
  catch (e) { debugError.value = e.message; return }
  const version = ++requestVersion
  verifying.value = true
  try {
    const data = await validateScenarioExtraction(props.scenarioId, props.envId, {
      session_id:result.value.session_id, response_id:result.value.response_id, extract_rules:rules,
    })
    if (version !== requestVersion) return
    result.value = { ...result.value, ...data }
    emit('debug', result.value)
    await nextTick()
    extractionPanel.value?.scrollIntoView({ block:'start', behavior:'smooth' })
  } catch (e) { if (version === requestVersion) debugError.value = e.message || '提取验证失败' }
  finally { if (version === requestVersion) verifying.value = false }
}
function clearDebug() {
  if (locked.value) return
  result.value = null; manualVariables.value = Object.create(null); debugError.value = ''
  emit('reset-debug')
}
async function copyResponse() {
  const body = result.value?.response_detail?.body
  const text = typeof body === 'string' ? body : JSON.stringify(body, null, 2)
  try {
    if (globalThis.isSecureContext && navigator.clipboard?.writeText) await navigator.clipboard.writeText(text)
    else {
      const area = document.createElement('textarea'); area.value = text; area.style.cssText = 'position:fixed;left:-9999px'
      document.body.appendChild(area); area.select()
      try { if (!document.execCommand('copy')) throw Error('copy') } finally { area.remove() }
    }
    copied.value = true
  } catch { debugError.value = '复制失败，请手动选择响应内容复制' }
}
</script>

<template>
  <Modal :title="debugMode ? '调试场景步骤' : '编辑场景步骤'" :max-width="920" :busy="locked" hide-scrollbar @close="emit('close')">
    <p class="step-hint">修改只作用于当前步骤。应用后请保存场景，用例库和其他步骤不受影响。</p>
    <div class="step-source"><span>来源用例：{{ step.source_case_name || '不可用' }}</span><button type="button" :disabled="locked || !step.source_case_id" @click="emit('reapply')">{{ busy ? '读取模板中…' : '重新应用模板' }}</button></div>
    <p v-if="step.missing_reason" class="step-error" role="alert">{{ step.missing_reason }}。请重新应用有效模板，或关闭窗口后移除此步骤。</p>
    <fieldset class="step-fields" :disabled="locked || !!step.missing_reason">
    <div class="step-field"><label for="step-name">步骤名称</label><input id="step-name" v-model="name" maxlength="100" /></div>
    <div class="step-request-line">
      <div class="step-field"><label for="step-method">请求方法</label><select id="step-method" v-model="method"><option v-for="item in ['GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS']" :key="item">{{ item }}</option></select></div>
      <div class="step-field"><label for="step-url">请求路径</label><input id="step-url" v-model="url" placeholder="/orders/{id}" /></div>
      <div class="step-field"><label for="step-status">期望状态码</label><input id="step-status" v-model.number="expectedStatus" type="number" min="100" max="599" /></div>
    </div>
    <RequestEditor ref="editor" v-model="request" :url="url" id-prefix="scenario-step-request" />
    <button class="advanced-toggle" type="button" :aria-expanded="advanced" @click="advanced = !advanced">高级配置 <span>断言与变量提取</span><span class="toggle-symbol">{{ advanced ? '收起' : '展开' }}</span></button>
    <div v-if="advanced" class="step-advanced">
      <div class="step-field"><label for="step-assertions">断言（JSON 数组）</label><textarea id="step-assertions" v-model="assertions" rows="4" placeholder='[{"type":"json_eq","path":"$.status","expected":"paid"}]'></textarea></div>
    </div>
    <p v-if="unsupported" class="step-hint">来源用例含 SQL、数据集或重试配置。场景链路仍只执行 HTTP、状态校验、断言和变量提取；这些来源配置会保留，压测导入时会提示处理。</p>
    <p v-if="error" role="alert" class="step-error">{{ error }}</p>
    </fieldset>
    <section v-if="debugVisible || result" ref="debugPanel" class="step-debug-panel" aria-label="单步调试结果">
      <div class="debug-heading"><strong>单步调试</strong><span>环境：{{ environmentName || '未选择' }}</span><button type="button" :disabled="locked" @click="clearDebug">清空调试变量</button></div>
      <p class="step-hint">发送请求会执行当前步骤；调试变量闲置 10 分钟后过期，切换场景、环境或刷新页面后清空。</p>
      <details v-if="Object.keys(variables || {}).length" class="debug-variables"><summary>临时调试变量（{{ Object.keys(variables).length }}）</summary><pre>{{ JSON.stringify(variables, null, 2) }}</pre></details>
      <p v-if="!result" class="debug-empty">点击下方“发送请求”，查看本步骤的响应。</p>
      <template v-else>
        <div class="debug-verdict"><span>实际状态 <b>{{ result.actual_status ?? '—' }}</b></span><span>期望 {{ result.expected_status }}</span><span :class="result.passed ? 'debug-pass' : 'debug-fail'">{{ result.passed ? '校验通过' : '校验未通过' }}</span><button v-if="result.response_detail" type="button" @click="copyResponse">{{ copied ? '已复制' : '复制响应' }}</button></div>
        <p v-if="result.error" class="step-error">{{ result.error }}</p>
        <div v-if="result.missing_variables?.length" class="missing-vars"><label v-for="variable in result.missing_variables" :key="variable">{{ variable }}<input v-model="manualVariables[variable]" :disabled="locked" :aria-label="`临时变量 ${variable}`" placeholder="填入本次调试使用的值" /></label><small>也可以先调试前置步骤并验证提取，再返回这里。</small></div>
        <p v-if="staleResponse" class="step-hint">请求配置已修改，下方保留的是上次响应。</p>
        <CaseResponse :result="result" />
      </template>
    </section>
    <div v-if="advanced || result" ref="extractionPanel" class="step-field extraction-config">
      <div class="extraction-heading"><label for="step-extracts">提取规则（JSON 对象）</label><button type="button" :disabled="locked || !result?.response_id || staleResponse" @click="verifyExtraction">{{ verifying ? '验证中…' : '验证提取' }}</button></div>
      <textarea id="step-extracts" v-model="extracts" :disabled="locked" rows="3" placeholder='{"order_id":"$.id"}'></textarea>
      <p class="step-hint">使用刚才的响应验证，不会重新发送请求。配置应用并保存场景后用于正式执行。</p>
      <div v-for="(row, index) in result?.extraction || []" :key="index" class="extraction-row" :class="row.passed ? 'debug-pass' : 'debug-fail'"><strong>{{ row.name || '提取结果' }}</strong><code v-if="row.passed">{{ JSON.stringify(row.value) }}</code><span v-else>{{ row.error }}</span></div>
    </div>
    <p v-if="debugError" class="step-error" role="alert">{{ debugError }}</p>
    <template #foot><button class="btn btn-primary debug-send" :disabled="locked || !!step.missing_reason" @click="send">{{ sending ? '发送中…' : '发送请求' }}</button><button class="btn btn-ghost" :disabled="locked" @click="emit('close')">取消</button><button class="btn btn-ghost" :disabled="locked || !!step.missing_reason" @click="apply">应用到当前步骤</button></template>
  </Modal>
</template>

<style scoped>
.step-debug-panel{margin-top:18px;padding-top:16px;border-top:1px solid var(--border)}.debug-heading,.debug-verdict,.extraction-heading{display:flex;align-items:center;flex-wrap:wrap;gap:10px;font-size:12px;margin-bottom:10px}.debug-heading strong{font-size:13px}.debug-heading>span{color:var(--text-muted)}.debug-heading button,.debug-verdict button,.extraction-heading button{margin-left:auto;padding:4px 0;border:0;background:none;color:var(--primary);font:inherit;font-size:12px;cursor:pointer}.debug-verdict{padding:10px 12px;border:1px solid var(--border);border-radius:7px;background:var(--surface-2);color:var(--text-muted)}.debug-verdict b{font-size:13px;color:var(--text)}.debug-pass{color:var(--pass-fg)}.debug-fail{color:var(--fail-fg)}.debug-empty{padding:18px;text-align:center;border:1px dashed var(--border);border-radius:8px;color:var(--text-muted);font-size:12px}.debug-variables{font-size:12px;color:var(--text-muted);margin-bottom:12px}.debug-variables summary{cursor:pointer}.debug-variables pre{white-space:pre-wrap;overflow-wrap:anywhere;padding:10px;border-radius:6px;background:var(--surface-2);max-height:150px;overflow:auto;font:11px/1.6 ui-monospace,Consolas,monospace}.missing-vars{padding:12px;background:var(--surface-2);border-radius:8px}.missing-vars label{display:flex;align-items:center;gap:12px;margin-bottom:8px;font-size:12px;overflow-wrap:anywhere}.missing-vars input{flex:1;min-width:0;height:32px;border:1px solid var(--border);border-radius:5px;background:var(--surface);color:var(--text);padding:0 8px;font:inherit}.missing-vars small{color:var(--text-muted);font-size:11px}.extraction-config{margin-top:18px}.extraction-heading label{margin:0}.extraction-row{display:flex;align-items:baseline;flex-wrap:wrap;gap:10px;font-size:12px;padding:8px 0;overflow-wrap:anywhere}.extraction-row code{white-space:pre-wrap;overflow-wrap:anywhere}.debug-send{margin-right:auto}button:disabled{opacity:.5;cursor:default}@media(max-width:640px){.debug-send,.debug-send~.btn{font-size:12px;padding:0 10px;height:34px}.debug-heading>span{font-size:11px}.missing-vars label{display:block}.missing-vars input{box-sizing:border-box;width:100%;display:block;margin-top:5px}}
.step-fields{border:0;padding:0;margin:0;min-width:0}.step-source{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 12px;margin-bottom:16px;border:1px solid var(--border);border-radius:7px;background:var(--surface-2);font-size:12px;color:var(--text-muted)}.step-source span{min-width:0;overflow-wrap:anywhere}.step-source button{flex:none;padding:4px 0;border:0;background:transparent;color:var(--primary);font:inherit;cursor:pointer}.step-source button:disabled{opacity:.5;cursor:default}
.step-hint{margin:0 0 16px;color:var(--text-muted);font-size:12px;line-height:1.7}.step-field{min-width:0;margin-bottom:16px}.step-field label{display:block;margin-bottom:7px;font-size:12px;font-weight:600;color:var(--text)}.step-field input,.step-field select,.step-field textarea{box-sizing:border-box;width:100%;min-width:0;border:1px solid var(--border);border-radius:7px;background:var(--surface-2);color:var(--text);padding:9px 11px;font-family:inherit;font-size:13px;line-height:1.5}.step-field input,.step-field select{height:39px}.step-field textarea{resize:vertical;font:12px/1.65 ui-monospace,Consolas,monospace}.step-field :is(input,select,textarea):focus{outline:2px solid var(--primary);outline-offset:1px}.step-request-line{display:grid;grid-template-columns:110px minmax(0,1fr) 125px;gap:12px}.advanced-toggle{display:flex;align-items:center;gap:12px;width:100%;margin-top:16px;padding:12px;border:1px solid var(--border);border-radius:8px;background:var(--surface-2);color:var(--text);font-family:inherit;font-weight:600;font-size:12px;text-align:left;cursor:pointer}.advanced-toggle span{color:var(--text-muted);font-weight:400;font-size:11px}.toggle-symbol{margin-left:auto}.step-advanced{padding-top:16px}.step-error{padding:10px 12px;color:var(--fail-fg);background:var(--fail-bg);font-size:12px;border-radius:7px}@media(max-width:640px){.step-request-line{grid-template-columns:1fr 1fr}.step-request-line>.step-field:nth-child(2){grid-column:1/-1;grid-row:2}.advanced-toggle{flex-wrap:wrap}}
</style>
