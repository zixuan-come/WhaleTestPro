<script setup>
import { ref } from 'vue'
import Modal from './Modal.vue'
import RequestEditor from './RequestEditor.vue'
import { cloneRequest, requestDraft, serializeRequest } from '../utils/requestConfig'

const props = defineProps({ step: { type: Object, required: true }, busy: Boolean })
const emit = defineEmits(['apply', 'close', 'reapply'])
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

function apply() {
  if (props.busy || props.step.missing_reason) return
  error.value = ''
  if (!name.value.trim()) { error.value = '请填写步骤名称'; return }
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
    emit('apply', { ...cloneRequest(props.step), ...fields, name:name.value.trim(), method:method.value,
      url:url.value.trim(), expected_status:Number(expectedStatus.value), assertions:checks, extract_rules:rules })
  } catch (e) { error.value = e.message; if (e.tab) editor.value?.focusError(e) }
}
</script>

<template>
  <Modal title="编辑场景步骤" :max-width="920" :busy="busy" hide-scrollbar @close="emit('close')">
    <p class="step-hint">修改只作用于当前步骤。应用后请保存场景，用例库和其他步骤不受影响。</p>
    <div class="step-source"><span>来源用例：{{ step.source_case_name || '不可用' }}</span><button type="button" :disabled="busy || !step.source_case_id" @click="emit('reapply')">{{ busy ? '读取模板中…' : '重新应用模板' }}</button></div>
    <p v-if="step.missing_reason" class="step-error" role="alert">{{ step.missing_reason }}。请重新应用有效模板，或关闭窗口后移除此步骤。</p>
    <fieldset class="step-fields" :disabled="busy || !!step.missing_reason">
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
      <div class="step-field"><label for="step-extracts">提取规则（JSON 对象）</label><textarea id="step-extracts" v-model="extracts" rows="3" placeholder='{"order_id":"$.id"}'></textarea></div>
    </div>
    <p v-if="unsupported" class="step-hint">来源用例含 SQL、数据集或重试配置。场景链路仍只执行 HTTP、状态校验、断言和变量提取；这些来源配置会保留，压测导入时会提示处理。</p>
    <p v-if="error" role="alert" class="step-error">{{ error }}</p>
    </fieldset>
    <template #foot><button class="btn btn-ghost" :disabled="busy" @click="emit('close')">取消</button><button class="btn btn-primary" :disabled="busy || !!step.missing_reason" @click="apply">应用到当前步骤</button></template>
  </Modal>
</template>

<style scoped>
.step-fields{border:0;padding:0;margin:0;min-width:0}.step-source{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 12px;margin-bottom:16px;border:1px solid var(--border);border-radius:7px;background:var(--surface-2);font-size:12px;color:var(--text-muted)}.step-source span{min-width:0;overflow-wrap:anywhere}.step-source button{flex:none;padding:4px 0;border:0;background:transparent;color:var(--primary);font:inherit;cursor:pointer}.step-source button:disabled{opacity:.5;cursor:default}
.step-hint{margin:0 0 16px;color:var(--text-muted);font-size:12px;line-height:1.7}.step-field{min-width:0;margin-bottom:16px}.step-field label{display:block;margin-bottom:7px;font-size:12px;font-weight:600;color:var(--text)}.step-field input,.step-field select,.step-field textarea{box-sizing:border-box;width:100%;min-width:0;border:1px solid var(--border);border-radius:7px;background:var(--surface-2);color:var(--text);padding:9px 11px;font-family:inherit;font-size:13px;line-height:1.5}.step-field input,.step-field select{height:39px}.step-field textarea{resize:vertical;font:12px/1.65 ui-monospace,Consolas,monospace}.step-field :is(input,select,textarea):focus{outline:2px solid var(--primary);outline-offset:1px}.step-request-line{display:grid;grid-template-columns:110px minmax(0,1fr) 125px;gap:12px}.advanced-toggle{display:flex;align-items:center;gap:12px;width:100%;margin-top:16px;padding:12px;border:1px solid var(--border);border-radius:8px;background:var(--surface-2);color:var(--text);font-family:inherit;font-weight:600;font-size:12px;text-align:left;cursor:pointer}.advanced-toggle span{color:var(--text-muted);font-weight:400;font-size:11px}.toggle-symbol{margin-left:auto}.step-advanced{padding-top:16px}.step-error{padding:10px 12px;color:var(--fail-fg);background:var(--fail-bg);font-size:12px;border-radius:7px}@media(max-width:640px){.step-request-line{grid-template-columns:1fr 1fr}.step-request-line>.step-field:nth-child(2){grid-column:1/-1;grid-row:2}.advanced-toggle{flex-wrap:wrap}}
</style>
