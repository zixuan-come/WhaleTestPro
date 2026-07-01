<script setup>
import { ref, computed, onMounted } from 'vue'
import { listCases, runChain } from '../api/case'
import { listInterfaces } from '../api/interface'
import { listEnvironments } from '../api/environment'
import Modal from '../components/Modal.vue'

const cases = ref([])
const interfaces = ref([])
const envs = ref([])
const loading = ref(true)
const error = ref('')

const search = ref('')
const selectedEnv = ref('')

// 执行链:存用例副本,每项一个 _uid(同一用例可重复加入,靠 _uid 区分)
const chain = ref([])
let uidSeq = 1

// 拖拽调序
const dragIdx = ref(null)

// 运行
const running = ref(false)
const showResult = ref(false)
const results = ref([])

const ifaceMap = computed(() => {
  const m = {}
  for (const it of interfaces.value) m[it.id] = it
  return m
})
function methodOf(caseObj) {
  const it = ifaceMap.value[caseObj.interface_id]
  return (it?.method || 'GET').toUpperCase()
}
function methodClass(m) { return 'm-' + (m || 'get').toLowerCase() }
function extractKeys(caseObj) {
  return caseObj.extract_rules ? Object.keys(caseObj.extract_rules) : []
}

const filteredCases = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return cases.value
  return cases.value.filter(c => c.name.toLowerCase().includes(q) || String(c.id).includes(q))
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [cs, ifs, es] = await Promise.all([listCases(), listInterfaces(), listEnvironments()])
    cases.value = cs
    interfaces.value = ifs
    envs.value = es
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function addToChain(c) {
  chain.value.push({ ...c, _uid: uidSeq++ })
}
function removeStep(i) {
  chain.value.splice(i, 1)
}
function clearChain() {
  chain.value = []
}

function onDragStart(i) { dragIdx.value = i }
function onDrop(i) {
  const from = dragIdx.value
  if (from == null || from === i) return
  const [moved] = chain.value.splice(from, 1)
  chain.value.splice(i, 0, moved)
  dragIdx.value = null
}

async function onRun() {
  if (!chain.value.length) return
  running.value = true
  try {
    const ids = chain.value.map(c => c.id)
    results.value = await runChain(ids, selectedEnv.value || undefined)
    showResult.value = true
  } catch (e) {
    alert(e.message || '执行失败')
  } finally {
    running.value = false
  }
}

const overallPassed = computed(() => results.value.length > 0 && results.value.every(r => r.passed))

onMounted(load)
</script>

<template>
  <div class="toolbar">
    <div class="tb-left">
      <span class="tb-title">场景编排</span>
      <span class="tb-sub">从左侧用例库拖入用例、排出执行顺序,变量沿链自动透传</span>
    </div>
    <div class="tb-right">
      <select v-model="selectedEnv" class="env-sel" title="执行环境">
        <option value="">不指定环境</option>
        <option v-for="e in envs" :key="e.id" :value="e.id">环境:{{ e.name }}</option>
      </select>
      <button class="btn btn-ghost" :disabled="!chain.length || running" @click="clearChain">清空</button>
      <button class="btn btn-primary" :disabled="!chain.length || running" @click="onRun">
        <svg v-if="!running" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 4l14 8-14 8V4Z" /></svg>
        <span v-else class="spin"></span>
        {{ running ? '执行中…' : `运行编排 (${chain.length})` }}
      </button>
    </div>
  </div>

  <div v-if="error" class="form-err">{{ error }}<button class="btn btn-ghost retry" @click="load">重试</button></div>

  <div class="board">
    <!-- 左:用例库 -->
    <div class="panel lib">
      <div class="panel-head">
        用例库
        <input v-model="search" class="lib-search" placeholder="搜索用例…" />
      </div>
      <div v-if="loading" class="state">加载中…</div>
      <div v-else-if="!cases.length" class="state">还没有测试用例,先去「测试用例」页创建</div>
      <div v-else-if="!filteredCases.length" class="state">没有匹配的用例</div>
      <div v-else class="lib-list">
        <div v-for="c in filteredCases" :key="c.id" class="lib-item">
          <span class="tag-method" :class="methodClass(methodOf(c))">{{ methodOf(c) }}</span>
          <span class="li-name"><span class="id">#{{ c.id }}</span>{{ c.name }}</span>
          <button class="add-btn" title="加入执行链" @click="addToChain(c)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14" /></svg>
          </button>
        </div>
      </div>
    </div>

    <!-- 右:执行链 -->
    <div class="panel flow">
      <div class="panel-head">
        执行链<span class="count">{{ chain.length }} 步</span>
      </div>
      <div v-if="!chain.length" class="state drop-hint">
        执行链为空。点左侧用例的「+」加入,拖动步骤可调整顺序。
      </div>
      <div v-else class="steps">
        <div
          v-for="(c, i) in chain"
          :key="c._uid"
          class="step"
          :class="{ dragging: dragIdx === i }"
          draggable="true"
          @dragstart="onDragStart(i)"
          @dragover.prevent
          @drop="onDrop(i)"
        >
          <span class="step-no">{{ i + 1 }}</span>
          <span class="grip">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 6h.01M8 12h.01M8 18h.01M16 6h.01M16 12h.01M16 18h.01" /></svg>
          </span>
          <span class="tag-method" :class="methodClass(methodOf(c))">{{ methodOf(c) }}</span>
          <span class="step-name"><span class="id">#{{ c.id }}</span>{{ c.name }}</span>
          <span v-if="extractKeys(c).length" class="extract" :title="'此步提取变量,供后续步骤引用'">
            提取: {{ extractKeys(c).join(', ') }}
          </span>
          <button class="del-step" title="移除" @click="removeStep(i)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </div>
      </div>
    </div>
  </div>

  <!-- 运行结果弹层 -->
  <Modal v-if="showResult" title="编排执行结果" @close="showResult = false">
    <div class="verdict">
      <span class="badge" :class="overallPassed ? 'b-pass' : 'b-fail'"><span class="dot"></span>{{ overallPassed ? '全链通过' : '存在失败' }}</span>
      <span class="muted">共 {{ results.length }} 步</span>
    </div>
    <div v-for="(r, i) in results" :key="i" class="res-step" :class="{ fail: !r.passed }">
      <span class="res-no">{{ i + 1 }}</span>
      <div class="res-body">
        <div class="res-top">
          <span class="badge" :class="r.passed ? 'b-pass' : 'b-fail'"><span class="dot"></span>{{ r.passed ? '通过' : '失败' }}</span>
          <span class="res-case">用例 #{{ r.case_id }}</span>
        </div>
        <div v-if="r.error" class="res-err">{{ r.error }}</div>
        <div v-else class="res-meta">
          期望 {{ r.expected_status }} · 实际 <span :class="{ bad: r.actual_status !== r.expected_status }">{{ r.actual_status }}</span>
          <span v-if="r.assertions?.length"> · 断言 {{ r.assertions.filter(a => a.passed).length }}/{{ r.assertions.length }}</span>
        </div>
      </div>
    </div>

    <template #foot>
      <button class="btn btn-primary" @click="showResult = false">关闭</button>
    </template>
  </Modal>
</template>

<style scoped>
.toolbar { display:flex; align-items:center; justify-content:space-between; gap:16px; margin-bottom:20px; flex-wrap:wrap; }
.tb-title { font-size:16px; font-weight:750; margin-right:12px; }
.tb-sub { font-size:12.5px; color:var(--text-muted); }
.tb-right { display:flex; align-items:center; gap:10px; }
.env-sel { height:32px; padding:0 10px; font-size:12.5px; color:var(--text);
  background:var(--surface-2); border:1px solid var(--border); border-radius:6px; font-family:inherit; }
.env-sel:focus { outline:none; border-color:var(--primary); }
.spin { width:14px; height:14px; border:2px solid rgba(255,255,255,.4); border-top-color:#fff;
  border-radius:50%; animation:spin .7s linear infinite; }
@keyframes spin { to { transform:rotate(360deg); } }

.board { display:grid; grid-template-columns:340px 1fr; gap:16px; align-items:start; }
.panel { background:var(--surface); border:1px solid var(--border); border-radius:14px;
  box-shadow:var(--shadow-sm); overflow:hidden; }
.panel-head { display:flex; align-items:center; justify-content:space-between; gap:12px;
  padding:15px 18px; border-bottom:1px solid var(--border); font-size:14px; font-weight:700; }
.count { font-size:12px; font-weight:500; color:var(--text-muted); }

.lib-search { height:30px; padding:0 10px; font-size:12.5px; color:var(--text); width:140px;
  background:var(--surface-2); border:1px solid var(--border); border-radius:6px; font-family:inherit; }
.lib-search:focus { outline:none; border-color:var(--primary); }
.lib-list { max-height:calc(100vh - 240px); overflow:auto; }
.lib-item { display:flex; align-items:center; gap:9px; padding:11px 16px;
  border-bottom:1px solid var(--border); font-size:13px; }
.lib-item:last-child { border-bottom:none; }
.li-name { flex:1; display:flex; align-items:center; gap:8px; min-width:0; font-weight:550;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.li-name .id, .step-name .id { color:var(--text-muted); font-family:ui-monospace,Consolas,monospace;
  font-size:11.5px; background:var(--surface-2); padding:2px 7px; border-radius:5px; flex:none; }
.add-btn { width:28px; height:28px; flex:none; display:grid; place-items:center; cursor:pointer;
  background:var(--surface-2); border:1px solid var(--border); border-radius:6px; color:var(--primary);
  transition:background .15s,border-color .15s; }
.add-btn svg { width:15px; height:15px; }
.add-btn:hover { border-color:var(--primary); background:var(--surface); }

.steps { padding:14px 16px; display:flex; flex-direction:column; gap:10px; }
.step { display:flex; align-items:center; gap:10px; padding:12px 14px; font-size:13px;
  background:var(--surface-2); border:1px solid var(--border); border-radius:10px; cursor:grab;
  transition:border-color .15s,opacity .15s; }
.step.dragging { opacity:.4; border-color:var(--primary); }
.step:hover { border-color:var(--primary); }
.step-no { width:22px; height:22px; flex:none; display:grid; place-items:center; border-radius:50%;
  background:var(--primary); color:#fff; font-size:12px; font-weight:700; }
.grip { color:var(--text-muted); display:flex; }
.grip svg { width:16px; height:16px; }
.step-name { flex:1; display:flex; align-items:center; gap:8px; min-width:0; font-weight:550;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.extract { font-size:11px; color:var(--primary); background:var(--surface); border:1px solid var(--border);
  padding:3px 9px; border-radius:6px; flex:none; font-family:ui-monospace,Consolas,monospace; }
.del-step { width:26px; height:26px; flex:none; display:grid; place-items:center; cursor:pointer;
  background:none; border:none; color:var(--text-muted); border-radius:6px; transition:color .15s,background .15s; }
.del-step svg { width:15px; height:15px; }
.del-step:hover { color:var(--fail-fg); background:var(--fail-bg); }

.state { padding:44px 20px; text-align:center; color:var(--text-muted); font-size:13px; }
.drop-hint { padding:60px 20px; line-height:1.7; }

.form-err { color:var(--fail-fg); font-size:12.5px; background:var(--fail-bg); padding:10px 14px;
  border-radius:8px; margin-bottom:16px; }
.retry { margin-left:12px; }

/* ===== 结果弹层 ===== */
.verdict { display:flex; align-items:center; gap:12px; margin-bottom:16px; }
.verdict .muted { color:var(--text-muted); font-size:12.5px; }
.res-step { display:flex; gap:12px; padding-bottom:14px; margin-bottom:14px; border-bottom:1px solid var(--border); }
.res-step:last-child { border-bottom:none; margin-bottom:0; padding-bottom:0; }
.res-no { width:24px; height:24px; flex:none; display:grid; place-items:center; border-radius:50%;
  background:var(--surface-2); border:1px solid var(--border); font-size:12px; font-weight:700; }
.res-step.fail .res-no { border-color:var(--fail-fg); color:var(--fail-fg); }
.res-body { flex:1; }
.res-top { display:flex; align-items:center; gap:10px; margin-bottom:6px; }
.res-case { font-size:12.5px; color:var(--text-muted); font-family:ui-monospace,Consolas,monospace; }
.res-meta { font-size:12.5px; color:var(--text-muted); }
.res-meta .bad { color:var(--fail-fg); font-weight:700; }
.res-err { font-size:12.5px; color:var(--fail-fg); background:var(--fail-bg); padding:8px 11px; border-radius:7px; }

/* ===== 响应式 ===== */
@media (max-width:900px) {
  .board { grid-template-columns:1fr; }
  .lib-list { max-height:300px; }
  .extract { display:none; }
}
@media (max-width:600px) {
  .toolbar { flex-direction:column; align-items:stretch; }
  .tb-right { flex-wrap:wrap; }
}
</style>
