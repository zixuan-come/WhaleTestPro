<script setup>
import { computed, nextTick, onScopeDispose, ref, watch } from 'vue'
import { runInterface } from '../api/interface'
import { useFeedback } from '../composables/feedback'
import { cloneRequest, requestConfig, requestDraft, serializeRequest } from '../utils/requestConfig'
import EnvironmentSelect from './EnvironmentSelect.vue'
import RequestEditor from './RequestEditor.vue'
import Cases from '../views/Cases.vue'

const props = defineProps({
  interfaceData: { type: Object, required: true }, environments: { type: Array, default: () => [] },
  unified: { type: Boolean, default: false }, caseItems: { type: Array, default: () => [] },
  modelValue: { type: [String, Number], default: '' }, initialTab: { type: String, default: 'debug' },
})
const emit = defineEmits(['close', 'edit', 'update:modelValue', 'create-case', 'select-case', 'busy'])
const { showMessage } = useFeedback()
const tab = ref(props.initialTab)
const draft = ref(requestDraft(requestConfig(props.interfaceData)))
const editor = ref(null), casesPanel = ref(null)
const running = ref(false), error = ref(''), result = ref(null), lastRequest = ref(null)
watch(running, value => emit('busy', value), { flush: 'sync' })
let version = 0
const environment = computed({ get: () => props.modelValue, set: value => { if (!running.value) emit('update:modelValue', value) } })
const methodClass = computed(() => 'm-' + props.interfaceData.method.toLowerCase())
const configFields = [ ['path_params', 'Path 参数'], ['params', 'Query 参数'], ['headers', 'Headers'], ['body', 'Body'] ]
watch(() => JSON.stringify(props.interfaceData), () => reset())
watch(draft, () => { error.value = '' }, { deep: true, flush: 'sync' })
onScopeDispose(() => { version += 1 })

function reset() {
  version += 1
  running.value = false
  draft.value = requestDraft(requestConfig(props.interfaceData))
  result.value = null
  lastRequest.value = null
  error.value = ''
}

async function send() {
  if (running.value) return
  error.value = ''
  let values
  try {
    values = serializeRequest(draft.value, props.interfaceData.url)
    if (!props.modelValue) throw Error('请选择执行环境')
  } catch (failure) {
    editor.value?.focusError(failure)
    error.value = failure.message
    return
  }
  const requestVersion = ++version
  const snapshot = cloneRequest(values)
  running.value = true
  try {
    const output = await runInterface(props.interfaceData.id, props.modelValue, undefined, values)
    if (version !== requestVersion) return
    result.value = output
    lastRequest.value = snapshot
  } catch (failure) {
    if (version === requestVersion) error.value = failure.message || '执行失败'
  } finally { if (version === requestVersion) running.value = false }
}

async function saveAsCase(fromResult = false) {
  if (running.value) return
  let values
  try {
    values = fromResult && lastRequest.value ? cloneRequest(lastRequest.value) : serializeRequest(draft.value, props.interfaceData.url)
  } catch (failure) {
    editor.value?.focusError(failure)
    error.value = failure.message
    return
  }
  if (props.unified) {
    emit('create-case', values, fromResult ? result.value?.response?.status_code || 200 : 200)
    return
  }
  tab.value = 'cases'
  await nextTick()
  if (!casesPanel.value) { showMessage('用例面板加载失败，请重试', 'error'); return }
  casesPanel.value.openCreate(values, fromResult ? result.value?.response?.status_code || 200 : 200)
}
</script>

<template>
  <section class="interface-workspace">
    <header class="workspace-heading">
      <div class="workspace-title"><button v-if="!unified" class="workspace-back" type="button" :disabled="running" @click="emit('close')">← 接口列表</button><h2>{{ interfaceData.name }}</h2><div class="workspace-url"><span class="tag-method" :class="methodClass">{{ interfaceData.method }}</span><code>{{ interfaceData.url }}</code></div></div>
      <button type="button" class="btn btn-ghost" :disabled="running" @click="emit('edit', interfaceData)">编辑接口</button>
    </header>
    <div class="workspace-tabs" role="tablist" aria-label="接口工作区">
      <button v-for="item in [{key:'config',label:'接口配置'},{key:'debug',label:'接口调试'},{key:'cases',label:'测试用例'}]" :id="'workspace-tab-' + item.key" :key="item.key" type="button" role="tab" :aria-selected="tab === item.key" :aria-controls="'workspace-panel-' + item.key" :disabled="running" :class="{ active: tab === item.key }" @click="tab = item.key">{{ item.label }}</button>
    </div>

    <section v-if="tab === 'config'" id="workspace-panel-config" class="workspace-config panel" role="tabpanel" aria-labelledby="workspace-tab-config">
      <div class="panel-head">接口默认配置</div>
      <dl class="config-summary"><div><dt>接口名称</dt><dd>{{ interfaceData.name }}</dd></div><div><dt>分类</dt><dd>{{ interfaceData.category || '未分类' }}</dd></div><div><dt>请求方法</dt><dd>{{ interfaceData.method }}</dd></div><div><dt>请求 URL</dt><dd><code>{{ interfaceData.url }}</code></dd></div></dl>
      <div class="config-values"><section v-for="[key, label] in configFields" :key="key"><h3>{{ label }}</h3><pre>{{ interfaceData[key] == null ? '未配置' : JSON.stringify(interfaceData[key], null, 2) }}</pre></section></div>
    </section>

    <section v-show="tab === 'debug'" id="workspace-panel-debug" class="debug-panel panel" role="tabpanel" aria-labelledby="workspace-tab-debug">
      <div class="debug-toolbar"><div class="debug-environment"><span>执行环境</span><EnvironmentSelect v-model="environment" :environments="environments" /></div><div class="debug-actions"><button type="button" class="btn btn-ghost" :disabled="running" @click="reset">重置参数</button><button type="button" class="btn btn-ghost" :disabled="running" @click="saveAsCase()">保存为测试用例</button><button type="button" class="btn btn-primary" :disabled="running" @click="send">{{ running ? '发送中…' : '发送请求' }}</button></div></div>
      <p class="debug-hint">这里的参数用于本次调试。保存为测试用例后，可单独维护参数和断言。</p>
      <RequestEditor ref="editor" v-model="draft" :url="interfaceData.url" :disabled="running" id-prefix="debug-request" />
      <div v-if="error" class="workspace-error" role="alert">{{ error }}</div>
      <section v-if="result" class="debug-result" aria-live="polite">
        <div class="result-heading"><h3>响应结果</h3><div class="result-meta"><strong :class="result.response?.status_code >= 400 || result.error ? 'failed' : 'passed'">{{ result.response?.status_code || '请求失败' }}</strong><span>{{ result.duration_ms }} ms</span></div><button v-if="lastRequest" type="button" class="btn btn-ghost" :disabled="running" @click="saveAsCase(true)">保存本次请求为用例</button></div>
        <p v-if="result.error" class="workspace-error">{{ result.error }}</p>
        <code v-if="result.request" class="actual-request">{{ result.request.method }} {{ result.request.url }}</code>
        <pre v-if="result.response">{{ JSON.stringify(result.response.body, null, 2) }}</pre>
      </section>
    </section>

    <section v-if="tab === 'cases'" id="workspace-panel-cases" role="tabpanel" aria-labelledby="workspace-tab-cases">
      <div v-if="unified" class="panel interface-case-list"><div class="panel-head"><span>测试用例 · {{ caseItems.length }}</span><button class="btn btn-primary" @click="emit('create-case', null, 200)">新建用例</button></div><p v-if="!caseItems.length" class="empty-case-list">暂无用例，点击「新建用例」添加。</p><button v-for="testCase in caseItems" :key="testCase.id" class="interface-case-row" type="button" @click="emit('select-case', testCase)"><strong>{{ testCase.name }}</strong><span>期望状态 {{ testCase.expected_status }}</span><span>打开 →</span></button></div>
      <Cases v-else ref="casesPanel" :key="interfaceData.id" :interface-id="interfaceData.id" :interface-data="interfaceData" embedded />
    </section>
  </section>
</template>

<style scoped>
.empty-case-list{padding:28px 20px;color:var(--text-muted);font-size:13px;text-align:center}.interface-case-row{display:flex;align-items:center;gap:16px;flex-wrap:wrap;width:100%;padding:16px 20px;border:0;border-bottom:1px solid var(--border);background:transparent;color:var(--text);text-align:left;font:13px inherit;cursor:pointer}.interface-case-row:hover{background:var(--surface-2)}.interface-case-row strong{flex:1;min-width:0;overflow-wrap:anywhere}.interface-case-row span{font-size:12px;color:var(--text-muted)}.interface-case-row:focus-visible{outline:2px solid var(--primary);outline-offset:-2px}

.interface-workspace{display:flex;flex-direction:column;gap:18px;min-width:0}.workspace-heading{display:flex;justify-content:space-between;align-items:center;gap:16px}.workspace-title{min-width:0}.workspace-title h2{margin:12px 0 10px;font-size:22px;line-height:1.4;overflow-wrap:anywhere;color:var(--text)}.workspace-back{border:0;padding:0;background:none;color:var(--text-muted);font:12px inherit;cursor:pointer}.workspace-back:hover{color:var(--primary)}.workspace-url{display:flex;align-items:center;gap:10px}.workspace-url code{min-width:0;overflow-wrap:anywhere;color:var(--text-muted);font:13px ui-monospace,Consolas,monospace}.workspace-tabs{display:flex;gap:6px;border-bottom:1px solid var(--border)}.workspace-tabs button{position:relative;padding:12px 18px;background:transparent;border:0;color:var(--text-muted);font:13px inherit;cursor:pointer}.workspace-tabs button.active{color:var(--primary);font-weight:650}.workspace-tabs button.active:after{content:'';position:absolute;height:3px;bottom:-1px;left:12px;right:12px;background:var(--primary);border-radius:3px}.workspace-tabs button:focus-visible,.workspace-back:focus-visible{outline:2px solid var(--primary);outline-offset:2px}
.config-summary{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:0;padding:20px}.config-summary dt{font-size:12px;color:var(--text-muted);margin-bottom:7px}.config-summary dd{margin:0;color:var(--text);font-size:13px;overflow-wrap:anywhere}.config-values{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:0 20px 20px}.config-values section{min-width:0}.config-values h3{font-size:12px;margin:0 0 8px}.config-values pre{min-height:60px;margin:0;padding:12px;background:var(--surface-2);border:1px solid var(--border);border-radius:8px;white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.6 ui-monospace,Consolas,monospace;color:var(--text-muted)}
.debug-panel{padding:20px}.debug-toolbar{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}.debug-environment{display:flex;align-items:center;gap:12px;font-size:12px;color:var(--text-muted)}.debug-actions{display:flex;gap:8px;flex-wrap:wrap}.debug-hint{margin:14px 0;color:var(--text-muted);font-size:12px;line-height:1.6}.workspace-error{margin:14px 0 0;padding:10px 12px;background:var(--fail-bg);color:var(--fail-fg);border-radius:8px;font-size:12px;line-height:1.6}.debug-result{margin-top:22px;padding-top:18px;border-top:1px solid var(--border)}.result-heading{display:flex;gap:16px;align-items:center;flex-wrap:wrap}.result-heading h3{margin:0;font-size:14px}.result-heading .btn{margin-left:auto}.result-meta{display:flex;gap:12px;align-items:center;font-size:12px;color:var(--text-muted)}.passed{color:var(--pass-fg)}.failed{color:var(--fail-fg)}.actual-request{display:block;margin:14px 0 8px;overflow-wrap:anywhere;font:12px ui-monospace,Consolas,monospace;color:var(--text-muted)}.debug-result pre{padding:14px;margin:0;max-height:400px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;background:var(--surface-2);border:1px solid var(--border);border-radius:9px;font:12.5px/1.6 ui-monospace,Consolas,monospace;color:var(--text)}
@media(max-width:700px){.workspace-heading{align-items:flex-start}.workspace-title h2{font-size:19px}.workspace-heading>.btn{flex:none}.debug-panel{padding:14px}.debug-toolbar,.debug-environment{align-items:stretch;flex-direction:column;width:100%}.debug-actions{display:grid;grid-template-columns:1fr 1fr}.debug-actions .btn-primary{grid-column:1/-1}.config-summary,.config-values{grid-template-columns:1fr}.result-heading .btn{margin-left:0}.workspace-tabs button{padding:12px}}
</style>
