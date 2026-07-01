<script setup>
import { ref, computed, onMounted } from 'vue'
import { listRecords, replayRecord } from '../api/traffic'
import Modal from '../components/Modal.vue'

const records = ref([])
const loading = ref(true)
const error = ref('')

const replayingId = ref(null)   // 正在回放的记录 id
const showResult = ref(false)
const result = ref(null)        // 回放返回结果
const resultErr = ref('')

const total = computed(() => records.value.length)
const getCount = computed(() => records.value.filter(r => (r.method || '').toUpperCase() === 'GET').length)
const writeCount = computed(() => records.value.filter(r => ['POST', 'PUT', 'DELETE', 'PATCH'].includes((r.method || '').toUpperCase())).length)
const pathCount = computed(() => new Set(records.value.map(r => r.path)).size)

function methodClass(m) {
  return 'm-' + (m || 'get').toLowerCase()
}

function statusClass(code) {
  if (code == null) return 'b-skip'
  if (code < 400) return 'b-pass'
  return 'b-fail'
}

function fmtTime(s) {
  if (!s) return '—'
  const d = new Date(s)
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

function fmtVal(v) {
  if (v === undefined) return '—'
  if (v === null) return 'null'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    records.value = await listRecords()
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function onReplay(rec) {
  replayingId.value = rec.id
  resultErr.value = ''
  result.value = null
  try {
    const res = await replayRecord(rec.id)
    if (res && res.error) {
      resultErr.value = res.error
    } else {
      result.value = res
    }
    showResult.value = true
  } catch (e) {
    resultErr.value = e.message || '回放失败'
    showResult.value = true
  } finally {
    replayingId.value = null
  }
}

function closeResult() {
  showResult.value = false
}

onMounted(load)
</script>

<template>
  <div class="cards">
    <div class="card"><div class="k">录制总数</div><div class="v pri">{{ total }}</div></div>
    <div class="card"><div class="k">查询类 GET</div><div class="v pass">{{ getCount }}</div></div>
    <div class="card"><div class="k">写操作类</div><div class="v fail">{{ writeCount }}</div></div>
    <div class="card"><div class="k">涉及接口</div><div class="v">{{ pathCount }}</div></div>
  </div>

  <div class="panel">
    <div class="panel-head">
      录制流量
      <span class="count">共 {{ total }} 条</span>
    </div>

    <div v-if="loading" class="state">加载中…</div>
    <div v-else-if="error" class="state err">
      {{ error }}
      <button class="btn btn-ghost retry" @click="load">重试</button>
    </div>
    <div v-else-if="!records.length" class="state">暂无录制流量,给被测接口打真实请求后这里会记录下来</div>

    <template v-else>
      <div class="row head">
        <span class="c-method">方法</span>
        <span class="c-path">路径</span>
        <span class="c-status">状态</span>
        <span class="c-time">录制时间</span>
        <span class="c-act">回放</span>
      </div>
      <div v-for="rec in records" :key="rec.id" class="row">
        <span class="c-method"><span class="tag-method" :class="methodClass(rec.method)">{{ (rec.method || 'GET').toUpperCase() }}</span></span>
        <span class="c-path" :title="rec.path"><span class="id">#{{ rec.id }}</span>{{ rec.path }}</span>
        <span class="c-status"><span class="badge" :class="statusClass(rec.response_status)"><span class="dot"></span>{{ rec.response_status ?? '—' }}</span></span>
        <span class="c-time">{{ fmtTime(rec.created_at) }}</span>
        <span class="c-act">
          <button class="btn btn-primary rep" :disabled="replayingId === rec.id" @click="onReplay(rec)">
            {{ replayingId === rec.id ? '回放中…' : '回放' }}
          </button>
        </span>
      </div>
    </template>
  </div>

  <!-- 回放结果弹层 -->
  <Modal v-if="showResult" title="回放结果" :max-width="680" @close="closeResult">
    <div v-if="resultErr" class="form-err">{{ resultErr }}</div>

    <template v-else-if="result">
      <div class="target">
        <span class="tag-method" :class="methodClass(result.method)">{{ (result.method || 'GET').toUpperCase() }}</span>
        <span class="path">{{ result.path }}</span>
      </div>

      <div class="status-cmp">
        <div class="s-box">
          <div class="s-k">录制状态</div>
          <div class="s-v">{{ result.recorded_status ?? '—' }}</div>
        </div>
        <svg class="arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
        <div class="s-box" :class="{ bad: result.recorded_status !== result.replayed_status }">
          <div class="s-k">回放状态</div>
          <div class="s-v">{{ result.replayed_status ?? '—' }}</div>
        </div>
      </div>

      <div class="diff-summary" :class="result.diff?.same ? 'ok' : 'bad'">
        <template v-if="result.diff?.same">
          <span class="badge b-pass"><span class="dot"></span>响应完全一致</span>
          <span class="txt">录制响应与本次回放逐字段比对无差异(动态字段已按规则智能忽略)</span>
        </template>
        <template v-else>
          <span class="badge b-fail"><span class="dot"></span>{{ result.diff?.diffs?.length || 0 }} 处差异</span>
          <span class="txt">以下字段回放值与录制值不符</span>
        </template>
      </div>

      <div v-if="!result.diff?.same && result.diff?.diffs?.length" class="difftbl">
        <div class="drow head">
          <span class="d-path">字段路径</span>
          <span class="d-rec">录制值</span>
          <span class="d-rep">回放值</span>
          <span class="d-reason">原因</span>
        </div>
        <div v-for="(d, i) in result.diff.diffs" :key="i" class="drow">
          <span class="d-path" :title="d.path">{{ d.path }}</span>
          <span class="d-rec" :title="fmtVal(d.recorded)">{{ fmtVal(d.recorded) }}</span>
          <span class="d-rep" :title="fmtVal(d.replayed)">{{ fmtVal(d.replayed) }}</span>
          <span class="d-reason">{{ d.reason || '值不同' }}</span>
        </div>
      </div>
    </template>

    <template #foot>
      <button class="btn btn-ghost" @click="closeResult">关闭</button>
    </template>
  </Modal>
</template>

<style scoped>
.cards { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:24px; }
.card { background:var(--surface); border:1px solid var(--border);
  border-radius:14px; padding:18px 20px; box-shadow:var(--shadow-sm); transition:border-color .15s; }
.card:hover { border-color:var(--primary); }
.card .k { font-size:12px; color:var(--text-muted); margin-bottom:10px; font-weight:550; }
.card .v { font-size:27px; font-weight:780; letter-spacing:-.5px; }
.card .v.pass { color:var(--pass-fg); }
.card .v.fail { color:var(--fail-fg); }
.card .v.pri { color:var(--primary); }

.row { display:grid; grid-template-columns:80px 1.7fr 88px 116px 84px; align-items:center; gap:12px;
  padding:13px 20px; border-bottom:1px solid var(--border); font-size:13px; transition:background .15s; }
.row:last-child { border-bottom:none; }
.row:not(.head):hover { background:var(--surface-2); }
.row.head { font-size:11.5px; font-weight:600; color:var(--text-muted);
  text-transform:uppercase; letter-spacing:.5px; background:var(--surface-2); }
.c-path { display:flex; align-items:center; gap:10px; font-weight:550;
  font-family:ui-monospace,Consolas,monospace; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.c-path .id { color:var(--text-muted); font-size:12px; background:var(--surface-2);
  padding:2px 8px; border-radius:6px; flex:none; }
.c-time { color:var(--text-muted); font-family:ui-monospace,Consolas,monospace; font-size:12px; }
.c-act { text-align:right; }
.rep { height:30px; padding:0 14px; font-size:12.5px; }

.state { padding:48px 20px; text-align:center; color:var(--text-muted); font-size:13px; }
.state.err { color:var(--fail-fg); }
.retry { margin-left:12px; }

/* ===== 弹层 ===== */
.target { display:flex; align-items:center; gap:10px; margin-bottom:18px; font-family:ui-monospace,Consolas,monospace; font-size:13px; }
.target .path { color:var(--text); word-break:break-all; }

.status-cmp { display:flex; align-items:center; gap:14px; margin-bottom:18px; }
.s-box { flex:1; background:var(--surface-2); border:1px solid var(--border); border-radius:12px; padding:14px 16px; text-align:center; }
.s-box.bad { border-color:var(--fail-fg); background:var(--fail-bg); }
.s-box .s-k { font-size:11.5px; color:var(--text-muted); margin-bottom:6px; }
.s-box .s-v { font-size:22px; font-weight:750; font-family:ui-monospace,Consolas,monospace; }
.arrow { width:22px; height:22px; color:var(--text-muted); flex:none; }

.diff-summary { display:flex; align-items:center; gap:12px; padding:12px 14px; border-radius:10px; margin-bottom:14px; flex-wrap:wrap; }
.diff-summary.ok { background:var(--pass-bg); }
.diff-summary.bad { background:var(--fail-bg); }
.diff-summary .txt { font-size:12px; color:var(--text-muted); }

.difftbl { border:1px solid var(--border); border-radius:10px; overflow:hidden; }
.drow { display:grid; grid-template-columns:1.4fr 1fr 1fr 1.3fr; gap:10px; padding:10px 14px;
  border-bottom:1px solid var(--border); font-size:12px; align-items:center; }
.drow:last-child { border-bottom:none; }
.drow.head { background:var(--surface-2); font-weight:600; color:var(--text-muted); font-size:11px;
  text-transform:uppercase; letter-spacing:.4px; }
.drow span { font-family:ui-monospace,Consolas,monospace; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.drow.head span { font-family:inherit; }
.d-rec { color:var(--text-muted); }
.d-rep { color:var(--fail-fg); font-weight:600; }
.d-reason { font-family:inherit !important; color:var(--text-muted); white-space:normal !important; }

.form-err { color:var(--fail-fg); font-size:12.5px; background:var(--fail-bg); padding:9px 12px; border-radius:8px; }

/* ===== 响应式 ===== */
@media (max-width:1100px) {
  .cards { grid-template-columns:repeat(2,1fr); }
}
@media (max-width:640px) {
  .cards { grid-template-columns:1fr; gap:12px; }
  .row { grid-template-columns:64px 1fr 72px; gap:8px; padding:12px 14px; }
  .c-status, .c-time { display:none; }
  .difftbl { display:none; }  /* 手机端只看差异条数摘要,明细回桌面看 */
}
</style>
