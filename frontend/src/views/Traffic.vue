<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { listRecords, getRecord, replayRecord, captureState, startCapture, stopCapture } from '../api/traffic'
import { listEnvironments } from '../api/environment'
import { useAuthStore } from '../stores/auth'
import { useFeedback } from '../composables/feedback'
import Modal from '../components/Modal.vue'
import EnvironmentSelect from '../components/EnvironmentSelect.vue'

const auth = useAuthStore(), { showMessage } = useFeedback()
const records = ref([]), capture = ref(null), environments = ref([])
const loading = ref(false), busy = ref(false), error = ref(''), page = ref(0), hasNext = ref(false), scope = ref('mine')
const selected = ref(null), modal = ref(''), modalLoading = ref(false), replaying = ref(false), modalError = ref(''), result = ref(null)
const envId = ref(''), headers = ref(''), params = ref(''), body = ref(''), ignored = ref('')
let generation = 0, modalGeneration = 0, timer
const pageSize = 20
const environment = computed(() => environments.value.find(item => String(item.id) === String(envId.value)))
const targetUrl = computed(() => environment.value && selected.value ? environment.value.base_url.replace(/\/$/, '') + selected.value.path : '')
const json = value => JSON.stringify(value ?? null, null, 2)
const fmtTime = value => value ? new Date(value.endsWith('Z') ? value : value + 'Z').toLocaleString('zh-CN', { hour12: false }) : '—'
const statusClass = code => code == null ? 'b-skip' : code < 400 ? 'b-pass' : 'b-fail'

async function load() {
  const version = ++generation, project = auth.currentProjectId
  if (!project) { records.value = []; capture.value = null; loading.value = false; return }
  loading.value = true; error.value = ''
  try {
    const [state, envs] = await Promise.all([captureState(), listEnvironments()])
    if (version !== generation) return
    capture.value = state; environments.value = envs
    if (scope.value === 'mine' && !state.capture_id) { records.value = []; hasNext.value = false; return }
    const rows = await listRecords({ limit: pageSize + 1, offset: page.value * pageSize, ...(scope.value === 'mine' ? { capture_id: state.capture_id } : {}) })
    if (version !== generation) return
    records.value = rows.slice(0, pageSize); hasNext.value = rows.length > pageSize
  } catch (err) { if (version === generation) error.value = err.message || '流量记录加载失败' }
  finally { if (version === generation) loading.value = false }
}
async function toggleCapture() {
  if (busy.value || !auth.currentProjectId) return
  busy.value = true; error.value = ''
  const project = auth.currentProjectId
  try {
    const wasActive = capture.value?.active
    const state = await (wasActive ? stopCapture() : startCapture())
    if (project !== auth.currentProjectId) return
    capture.value = state; scope.value = 'mine'; page.value = 0
    showMessage(wasActive ? '录制已停止' : '录制已开始，请前往接口测试发送请求', 'success')
    await load()
  } catch (err) { if (project === auth.currentProjectId) error.value = err.message || '录制操作失败' }
  finally { if (project === auth.currentProjectId) busy.value = false }
}
function changeScope(value) { scope.value = value; page.value = 0; load() }
function changePage(delta) { if (!loading.value) { page.value += delta; load() } }
function closeModal() { if (replaying.value) return; ++modalGeneration; modal.value = ''; selected.value = null; result.value = null; headers.value = ''; params.value = ''; body.value = ''; modalError.value = '' }
async function openRecord(record, mode) {
  if (replaying.value) return
  const version = ++modalGeneration, project = auth.currentProjectId
  modal.value = mode; modalLoading.value = true; modalError.value = ''; selected.value = null; result.value = null; envId.value = ''; ignored.value = ''
  try {
    const detail = await getRecord(record.id)
    if (version !== modalGeneration || project !== auth.currentProjectId) return
    selected.value = detail; headers.value = json(detail.request_headers || {}); params.value = json(detail.request_params || {}); body.value = json(detail.request_body)
  } catch (err) { if (version === modalGeneration) modalError.value = err.message || '请求详情加载失败' }
  finally { if (version === modalGeneration) modalLoading.value = false }
}
function parseObject(value, name) {
  const parsed = JSON.parse(value)
  if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') throw Error(name + ' 必须为 JSON 对象')
  return parsed
}
async function sendReplay() {
  if (replaying.value || !selected.value) return
  modalError.value = ''
  if (!environment.value) { modalError.value = '请选择回放环境'; return }
  let payload
  try {
    payload = { env_id: Number(envId.value), headers: parseObject(headers.value, 'Headers'), params: parseObject(params.value, 'Query'), body: JSON.parse(body.value), field_rules: Object.fromEntries(ignored.value.split(/[,，\n]/).map(s => s.trim()).filter(Boolean).map(key => [key, 'ignore'])) }
    if (Object.values(payload.headers).some(value => typeof value !== 'string')) throw Error('Headers 的值必须是字符串')
  } catch (err) { modalError.value = err instanceof SyntaxError ? '请求配置不是合法 JSON，请检查后再发送' : err.message; return }
  const version = modalGeneration, project = auth.currentProjectId
  replaying.value = true
  try {
    const response = await replayRecord(selected.value.id, payload)
    if (version !== modalGeneration || project !== auth.currentProjectId) return
    result.value = response
  } catch (err) { if (version === modalGeneration) modalError.value = err.message || '回放失败' }
  finally { if (version === modalGeneration) replaying.value = false }
}
watch(() => auth.currentProjectId, () => {
  ++modalGeneration; modal.value = ''; selected.value = null; result.value = null; replaying.value = false; busy.value = false
  headers.value = ''; params.value = ''; body.value = ''; envId.value = ''; environments.value = []; capture.value = null; records.value = []; page.value = 0
  load()
}, { immediate: true })
timer = setInterval(() => { if (capture.value?.active && !loading.value && !busy.value && !modal.value) load() }, 5000)
onBeforeUnmount(() => { clearInterval(timer); ++generation; ++modalGeneration })
</script>

<template>
  <section class="panel capture-panel">
    <div class="capture-heading"><div><h2>录制接口请求</h2><p>开始录制 → 前往接口测试调试接口 → 停止录制 → 选择环境回放</p></div><span class="badge" :class="capture?.active ? 'b-pass' : 'b-skip'"><span class="dot"></span>{{ capture?.active ? '正在录制' : '未在录制' }}</span></div>
    <div class="capture-actions"><button class="btn" :class="capture?.active ? 'btn-ghost' : 'btn-primary'" :disabled="busy || loading || !auth.currentProjectId" @click="toggleCapture">{{ busy ? '处理中…' : capture?.active ? '停止录制' : '开始录制' }}</button><RouterLink to="/interfaces" class="btn btn-ghost">前往接口测试</RouterLink><span v-if="capture?.capture_id" class="muted">最近一次 {{ capture.count }} 条 · {{ fmtTime(capture.started_at) }} 开始</span></div>
    <p class="hint">只录制你在当前项目「接口调试」中发送的请求，切换页面后继续录制；一小时后自动结束，最多 1000 条。敏感字段会脱敏。</p>
  </section>
  <div v-if="error" class="form-err" role="alert">{{ error }} <button class="text-btn" @click="load">重试</button></div>
  <section class="panel records-panel" :aria-busy="loading">
    <div class="panel-head"><h2>流量记录</h2><div class="list-actions"><div class="scope-tabs" role="group" aria-label="记录范围"><button :class="{active:scope === 'mine'}" @click="changeScope('mine')">我的最近录制</button><button :class="{active:scope === 'all'}" @click="changeScope('all')">项目全部记录</button></div><button class="btn btn-ghost" :disabled="loading" @click="load">刷新</button></div></div>
    <div v-if="loading" class="state">加载中…</div>
    <div v-else-if="!records.length" class="state"><strong>{{ scope === 'mine' ? '还没有录到请求' : '暂无流量记录' }}</strong><p>{{ capture?.active ? '前往接口测试，打开接口调试并发送请求，然后回到这里查看。' : '点击「开始录制」，再到接口调试发送请求。' }}</p></div>
    <template v-else>
      <div class="traffic-row row-head"><span>接口 / 路径</span><span>状态码</span><span>耗时</span><span>录制时间</span><span>操作</span></div>
      <div v-for="record in records" :key="record.id" class="traffic-row">
        <div class="request-name"><span class="tag-method" :class="'m-' + record.method.toLowerCase()">{{ record.method }}</span><div><strong>{{ record.interface_name || record.path }}</strong><small :title="record.path">{{ record.path }}<span v-if="record.source !== 'debug'"> · 历史入站记录</span></small></div></div>
        <span class="badge" :class="statusClass(record.response_status)">{{ record.response_status ?? '—' }}</span><span class="muted response-time">{{ record.duration_ms == null ? '—' : record.duration_ms + ' ms' }}</span><time class="muted">{{ fmtTime(record.created_at) }}</time>
        <div class="row-actions"><button class="text-btn" @click="openRecord(record,'detail')">详情</button><button class="text-btn" @click="openRecord(record,'replay')">回放</button></div>
      </div>
    </template>
    <div class="pagination"><span>第 {{ page + 1 }} 页 · 每页 20 条</span><div><button class="btn btn-ghost" :disabled="!page || loading" @click="changePage(-1)">上一页</button><button class="btn btn-ghost" :disabled="!hasNext || loading" @click="changePage(1)">下一页</button></div></div>
  </section>

  <Modal v-if="modal" :title="modal === 'detail' ? '录制请求详情' : result ? '回放结果' : '配置回放'" :max-width="820" :busy="replaying" hide-scrollbar @close="closeModal">
    <div class="traffic-modal">
      <div v-if="modalLoading" class="state">加载请求详情…</div>
      <div v-if="modalError" class="form-err" role="alert">{{ modalError }}</div>
      <template v-if="selected">
        <div class="request-summary"><span class="tag-method" :class="'m-' + selected.method.toLowerCase()">{{ selected.method }}</span><strong>{{ selected.interface_name || selected.path }}</strong><code>{{ selected.path }}</code></div>
        <template v-if="modal === 'detail'">
          <div class="detail-meta"><span>状态码 {{ selected.response_status ?? '—' }}</span><span>耗时 {{ selected.duration_ms ?? '—' }} ms</span><span>{{ fmtTime(selected.created_at) }}</span></div>
          <details open><summary>Query 参数</summary><pre>{{ json(selected.request_params) }}</pre></details><details><summary>Headers</summary><pre>{{ json(selected.request_headers) }}</pre></details><details><summary>请求 Body</summary><pre>{{ json(selected.request_body) }}</pre></details><details open><summary>录制响应</summary><pre>{{ json(selected.response_body) }}</pre></details>
        </template>
        <template v-else-if="!result">
          <label class="field"><span>回放环境 <span class="required">*</span></span><EnvironmentSelect v-model="envId" :environments="environments" placeholder="请选择回放环境" /></label><p v-if="targetUrl" class="target-url">目标：{{ targetUrl }}</p><p v-if="!environments.length" class="hint">当前项目没有环境，请先到环境管理创建。</p>
          <p class="hint">回放会向所选环境发送一次真实请求；写入接口可能改变该环境的数据。X-Shadow 仅为提示，数据隔离需要被测系统支持。</p>
          <details class="request-config" open><summary>请求配置</summary><p class="hint">沿用录制时的请求。请替换 *** 脱敏值，可填写环境变量，例如 Bearer ${token}。这里只修改本次回放。</p><label class="field"><span>Headers · JSON 对象</span><textarea v-model="headers" rows="3" spellcheck="false" /></label><label class="field"><span>Query · JSON 对象</span><textarea v-model="params" rows="3" spellcheck="false" /></label><label class="field"><span>Body · JSON，没有请求体填 null</span><textarea v-model="body" rows="4" spellcheck="false" /></label></details>
          <label class="field"><span>额外忽略的响应字段（可选）</span><input v-model="ignored" placeholder="例如 request_id, trace_id，用逗号分隔" /></label><p class="hint">默认忽略 token；id 比较整数类型，created_at / updated_at 比较字符串类型。状态码始终比较。</p>
        </template>
        <template v-else>
          <p class="target-url">回放目标：{{ result.target_url || targetUrl }}</p>
          <div class="comparison-verdict" :class="result.diff?.same ? 'passed' : 'failed'"><strong>{{ result.diff?.same ? '比较通过' : '发现差异' }}</strong><span>录制状态码 {{ result.recorded_status }} → 回放状态码 {{ result.replayed_status }}</span></div>
          <p class="hint">比较结果已应用动态字段规则，敏感字段已脱敏。</p>
          <div v-for="(diff,index) in result.diff?.diffs || []" :key="index" class="diff-item"><strong>{{ diff.path }}</strong><span>{{ diff.reason || '值不同' }}</span><div><small>录制值</small><pre>{{ json(diff.recorded) }}</pre></div><div><small>回放值</small><pre>{{ json(diff.replayed) }}</pre></div></div>
          <details><summary>录制响应</summary><pre>{{ json(result.recorded_body) }}</pre></details><details><summary>回放响应</summary><pre>{{ json(result.replayed_body) }}</pre></details>
        </template>
      </template>
    </div>
    <template #foot><button class="btn btn-ghost" :disabled="replaying" @click="closeModal">关闭</button><button v-if="modal === 'detail' && selected" class="btn btn-primary" @click="modal = 'replay'">配置回放</button><button v-else-if="result" class="btn btn-ghost" @click="result = null">重新配置</button><button v-else-if="modal === 'replay' && selected" class="btn btn-primary" :disabled="replaying" @click="sendReplay">{{ replaying ? '回放中…' : '发送回放' }}</button></template>
  </Modal>
</template>

<style scoped>
h2 { margin:0; font-size:15px; font-weight:650; }
.capture-panel { padding:20px 22px; margin-bottom:20px; }
.capture-heading,.capture-actions,.list-actions,.row-actions,.detail-meta,.pagination,.pagination>div { display:flex; align-items:center; gap:12px; }
.capture-heading { justify-content:space-between; gap:16px; }
.capture-heading p { margin:8px 0 0; font-size:13px; color:var(--text-muted); line-height:1.6; }
.capture-actions { margin-top:16px; flex-wrap:wrap; }
.hint,.muted { font-size:12px; color:var(--text-muted); line-height:1.65; }
.hint { margin:10px 0 0; }
.list-actions { flex-wrap:wrap; }
.scope-tabs { display:flex; padding:3px; background:var(--surface-2); border-radius:8px; gap:3px; }
.scope-tabs button { border:0; background:transparent; padding:6px 10px; border-radius:6px; color:var(--text-muted); cursor:pointer; font:inherit; font-size:12px; }
.scope-tabs button.active { background:var(--surface); color:var(--primary); box-shadow:var(--shadow-sm); }
.traffic-row { display:grid; grid-template-columns:minmax(150px,1fr) 64px 70px 160px 85px; align-items:center; gap:16px; padding:11px 20px; border-bottom:1px solid var(--border); font-size:12px; }
.traffic-row:not(.row-head):hover { background:var(--surface-2); }
.row-head { background:var(--surface-2); color:var(--text-muted); font-size:11px; }
.request-name { display:flex; gap:10px; align-items:center; min-width:0; }
.request-name>div { min-width:0; }
.request-name strong,.request-name small { display:block; white-space:nowrap; text-overflow:ellipsis; overflow:hidden; }
.request-name strong { font-size:13px; font-weight:550; }
.request-name small { color:var(--text-muted); font-size:11px; margin-top:3px; }
.traffic-row>.badge { justify-self:start; }
.text-btn { border:0; background:transparent; color:var(--primary); cursor:pointer; font:inherit; font-size:12px; padding:5px 0; }
.text-btn:hover { text-decoration:underline; }
button:focus-visible { outline:2px solid var(--primary); outline-offset:2px; }
.pagination { padding:12px 20px; justify-content:space-between; color:var(--text-muted); font-size:12px; }
.pagination .btn { height:30px; padding:0 10px; font-size:12px; }
.state { padding:40px 20px; text-align:center; color:var(--text-muted); font-size:13px; }
.state p { line-height:1.7; }
.form-err { padding:10px 12px; margin-bottom:12px; border-radius:8px; background:var(--fail-bg); color:var(--fail-fg); font-size:12px; }
.traffic-modal { display:flex; flex-direction:column; gap:12px; }
.request-summary { display:flex; gap:10px; align-items:center; flex-wrap:wrap; font-size:13px; overflow-wrap:anywhere; }
.request-summary code { flex-basis:100%; color:var(--text-muted); font-size:12px; }
.detail-meta { flex-wrap:wrap; font-size:12px; color:var(--text-muted); }
.traffic-modal details { border:1px solid var(--border); border-radius:9px; padding:10px 12px; min-width:0; }
summary { cursor:pointer; font-size:13px; font-weight:550; }
pre { margin:10px 0 0; padding:10px; background:var(--surface-2); border-radius:7px; font:12px/1.6 ui-monospace,Consolas,monospace; white-space:pre-wrap; overflow-wrap:anywhere; }
.field { display:flex; flex-direction:column; gap:7px; margin:0; font-size:12px; }
.request-config .field { margin-top:12px; }
.field textarea { min-height:68px; font:12px/1.6 ui-monospace,Consolas,monospace; resize:vertical; scrollbar-width:none; }
.field textarea,.field input { width:100%; box-sizing:border-box; color:var(--text); background:var(--surface-2); border:1px solid var(--border); border-radius:8px; padding:9px 11px; }
.field input { min-height:36px; font:inherit; }
.field textarea:focus,.field input:focus { border-color:var(--primary); outline:2px solid var(--ring); }
.field textarea::-webkit-scrollbar { display:none; }
.required { color:var(--fail-fg); }
.target-url { margin:0; overflow-wrap:anywhere; color:var(--text-muted); font-size:12px; }
.comparison-verdict { display:flex; flex-wrap:wrap; gap:10px; align-items:center; padding:12px; border-radius:9px; font-size:12px; }
.comparison-verdict.passed { background:var(--pass-bg); color:var(--pass-fg); }
.comparison-verdict.failed { background:var(--fail-bg); color:var(--fail-fg); }
.diff-item { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:8px; border:1px solid var(--border); padding:12px; border-radius:8px; font-size:12px; overflow-wrap:anywhere; }
.diff-item>span,.diff-item small { color:var(--text-muted); }
.diff-item>span { text-align:right; }
@media(max-width:1050px) { .traffic-row { grid-template-columns:minmax(150px,1fr) 60px 70px 85px; } .traffic-row time,.row-head>span:nth-child(4) { display:none; } }
@media(max-width:640px) { .capture-panel { padding:16px; } .capture-heading { align-items:flex-start; } .capture-heading .badge { flex:none; } .panel-head { align-items:flex-start; gap:12px; flex-direction:column; padding:16px; } .traffic-row { grid-template-columns:minmax(0,1fr) 85px; gap:8px; padding:10px 14px; } .traffic-row>.badge,.response-time,.row-head { display:none; } .request-name { align-items:flex-start; flex-direction:column; gap:5px; } .pagination { padding:12px; flex-wrap:wrap; gap:8px; } .diff-item { grid-template-columns:minmax(0,1fr); } .diff-item>span { text-align:left; } .capture-actions .muted { flex-basis:100%; } }
</style>
