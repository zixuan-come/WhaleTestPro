<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { listCases } from '../api/case'
import { listInterfaces } from '../api/interface'
import { listEnvironments } from '../api/environment'
import {
  listScenarios, getScenario, createScenario, updateScenario, deleteScenario, runScenario,
} from '../api/scenario'
import { useAuthStore } from '../stores/auth'
import Modal from '../components/Modal.vue'

const auth = useAuthStore()

// —— 数据源 ——
const scenarios = ref([])
const cases = ref([])
const interfaces = ref([])
const envs = ref([])
const loading = ref(true)
const error = ref('')

// —— 当前选中的场景 ——
const currentId = ref(null)              // null=未选;数字=编辑中
const currentName = ref('')
const currentDesc = ref('')
const chain = ref([])                    // [{case obj}] 有序
// 快照:加载/保存时打一份,dirty = 当前 vs 快照 (避免用 watch 追踪的时序 bug)
const originalSnapshot = ref(null)

const dirty = computed(() => {
  if (!currentId.value || !originalSnapshot.value) return false
  const o = originalSnapshot.value
  if (currentName.value !== o.name) return true
  if ((currentDesc.value || '') !== (o.description || '')) return true
  const currentIds = chain.value.map(c => c.id).join(',')
  const originalIds = (o.case_ids || []).join(',')
  return currentIds !== originalIds
})

function snapshotCurrent() {
  originalSnapshot.value = {
    name: currentName.value,
    description: currentDesc.value || '',
    case_ids: chain.value.map(c => c.id),
  }
}

// —— 用例库 ——
const search = ref('')

// —— 拖拽 ——
const dragIdx = ref(null)

// —— 跑测试 ——
const selectedEnv = ref('')
const running = ref(false)
const showResult = ref(false)
const results = ref([])

// —— 新建场景弹层 ——
const showNew = ref(false)
const newName = ref('')
const newDesc = ref('')
const newErr = ref('')

// —— 派生 ——
const caseMap = computed(() => {
  const m = {}
  for (const c of cases.value) m[c.id] = c
  return m
})
const ifaceMap = computed(() => {
  const m = {}
  for (const it of interfaces.value) m[it.id] = it
  return m
})
function methodOf(c) { return (ifaceMap.value[c?.interface_id]?.method || 'GET').toUpperCase() }
function methodClass(m) { return 'm-' + (m || 'get').toLowerCase() }

const filteredCases = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return cases.value
  return cases.value.filter(c => c.name.toLowerCase().includes(q))
})

const overallPassed = computed(() => results.value.length > 0 && results.value.every(r => r.passed))

// —— 加载全量 ——
async function load() {
  loading.value = true
  error.value = ''
  try {
    const [scs, cs, ifs, es] = await Promise.all([
      listScenarios(), listCases(), listInterfaces(), listEnvironments(),
    ])
    scenarios.value = scs
    cases.value = cs
    interfaces.value = ifs
    envs.value = es

    // 恢复上次选的环境(跨 Cases/Orchestration 共用同一记忆)
    const remembered = auth.getPreferredEnv(auth.currentProjectId)
    if (remembered && es.some(e => String(e.id) === String(remembered))) {
      selectedEnv.value = String(remembered)
    } else if (remembered) {
      auth.setPreferredEnv(auth.currentProjectId, null)
    }
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

watch(selectedEnv, (v) => auth.setPreferredEnv(auth.currentProjectId, v || null))

// —— 场景操作 ——
async function selectScenario(sc) {
  if (dirty.value && !confirm('当前场景有未保存改动,切换会丢弃。继续?')) return
  try {
    // 拉全量数据(list 接口跟 get 应该一致,但保险起见)
    const full = await getScenario(sc.id)
    currentId.value = full.id
    currentName.value = full.name
    currentDesc.value = full.description || ''
    // 按 case_ids 顺序找回 case 对象;丢失的用例跳过(留个 console.warn)
    const ids = full.case_ids || []
    const found = ids.map(id => caseMap.value[id]).filter(Boolean)
    const missing = ids.length - found.length
    if (missing > 0) {
      console.warn(`场景 "${full.name}" 有 ${missing} 个用例已被删除,已从链上跳过`)
    }
    chain.value = found.map(c => ({ ...c, _uid: `${c.id}-${Math.random().toString(36).slice(2, 8)}` }))
    snapshotCurrent()
  } catch (e) {
    alert(e.message || '加载场景失败')
  }
}

function openNewScenario() {
  newName.value = ''
  newDesc.value = ''
  newErr.value = ''
  showNew.value = true
}
async function submitNewScenario() {
  const nm = newName.value.trim()
  if (!nm) { newErr.value = '请输入场景名'; return }
  try {
    const sc = await createScenario({ name: nm, description: newDesc.value.trim() || null, case_ids: [] })
    scenarios.value.unshift(sc)
    showNew.value = false
    // 自动选中新建的
    await selectScenario(sc)
  } catch (e) {
    newErr.value = e.message || '创建失败'
  }
}

async function saveCurrent() {
  if (!currentId.value) return
  try {
    const payload = {
      name: currentName.value.trim() || '未命名',
      description: currentDesc.value.trim() || null,
      case_ids: chain.value.map(c => c.id),
    }
    const sc = await updateScenario(currentId.value, payload)
    // 更新列表里的对应项
    const idx = scenarios.value.findIndex(s => s.id === sc.id)
    if (idx !== -1) scenarios.value[idx] = sc
    snapshotCurrent()
  } catch (e) {
    alert(e.message || '保存失败')
  }
}

async function deleteCurrent() {
  if (!currentId.value) return
  if (!confirm(`确认删除场景「${currentName.value}」? (关联的用例不会删)`)) return
  try {
    await deleteScenario(currentId.value)
    scenarios.value = scenarios.value.filter(s => s.id !== currentId.value)
    clearEditor()
  } catch (e) {
    alert(e.message || '删除失败')
  }
}

function clearEditor() {
  currentId.value = null
  currentName.value = ''
  currentDesc.value = ''
  chain.value = []
  originalSnapshot.value = null
}

// —— chain 操作 ——
function addToChain(c) {
  if (!currentId.value) { alert('请先选择或新建一个场景'); return }
  chain.value.push({ ...c, _uid: `${c.id}-${Math.random().toString(36).slice(2, 8)}` })
}
function removeStep(i) {
  chain.value.splice(i, 1)
}
function onDragStart(i) { dragIdx.value = i }
function onDrop(i) {
  const from = dragIdx.value
  if (from === null || from === i) { dragIdx.value = null; return }
  const [moved] = chain.value.splice(from, 1)
  chain.value.splice(i, 0, moved)
  dragIdx.value = null
}

// —— 跑 ——
async function onRun() {
  if (!currentId.value) return
  if (dirty.value && !confirm('当前场景有未保存改动,跑的是保存过的版本。要不要先保存?')) return
  running.value = true
  try {
    const data = await runScenario(currentId.value, selectedEnv.value || undefined)
    results.value = Array.isArray(data) ? data : [data]
    showResult.value = true
  } catch (e) {
    alert(e.message || '执行失败')
  } finally {
    running.value = false
  }
}

function fmtJson(v) { return JSON.stringify(v, null, 2) }

onMounted(load)
</script>

<template>
  <div v-if="loading" class="state">加载中…</div>
  <div v-else-if="error" class="state err">
    {{ error }}
    <button class="btn btn-ghost" @click="load">重试</button>
  </div>

  <div v-else class="three-col">
    <!-- ==================== 左:场景列表 ==================== -->
    <aside class="col-left panel">
      <div class="panel-head">
        场景
        <button class="btn btn-primary btn-sm" @click="openNewScenario">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14" /></svg>
          新建
        </button>
      </div>
      <div v-if="!scenarios.length" class="empty">还没场景,点右上角"新建"</div>
      <div v-else class="sc-list">
        <div v-for="sc in scenarios" :key="sc.id"
             class="sc-item"
             :class="{ active: sc.id === currentId }"
             @click="selectScenario(sc)">
          <div class="sc-name">{{ sc.name }}</div>
          <div class="sc-meta">
            <span class="sc-count">{{ (sc.case_ids || []).length }} 步</span>
            <span v-if="sc.description" class="sc-desc" :title="sc.description">{{ sc.description }}</span>
          </div>
        </div>
      </div>
    </aside>

    <!-- ==================== 中:用例库 ==================== -->
    <section class="col-mid panel">
      <div class="panel-head">
        用例库
        <input v-model="search" class="lib-search" placeholder="按名称过滤…" />
      </div>
      <div v-if="!filteredCases.length" class="empty">没有匹配的用例</div>
      <div v-else class="lib-list">
        <div v-for="(c, i) in filteredCases" :key="c.id" class="lib-item">
          <span class="tag-method" :class="methodClass(methodOf(c))">{{ methodOf(c) }}</span>
          <span class="li-name"><span class="id">#{{ i + 1 }}</span>{{ c.name }}</span>
          <button class="icon-btn add" title="加到当前场景" @click="addToChain(c)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14" /></svg>
          </button>
        </div>
      </div>
    </section>

    <!-- ==================== 右:编辑区 ==================== -->
    <section class="col-right panel">
      <div v-if="!currentId" class="empty tall">
        左侧选一个场景开始编辑,或点"新建"创建新场景
      </div>
      <template v-else>
        <div class="panel-head editor-head">
          <div class="editor-meta">
            <input v-model="currentName" class="editor-name" placeholder="场景名" />
            <span v-if="dirty" class="dirty-dot" title="有未保存改动">●</span>
          </div>
          <div class="editor-actions">
            <select v-model="selectedEnv" class="env-sel" title="跑测试用的环境">
              <option value="">不指定环境</option>
              <option v-for="e in envs" :key="e.id" :value="e.id">环境:{{ e.name }}</option>
            </select>
            <button class="btn btn-ghost btn-sm" @click="deleteCurrent">删除</button>
            <button class="btn btn-ghost btn-sm" @click="saveCurrent" :disabled="!dirty">保存</button>
            <button class="btn btn-primary btn-sm" @click="onRun" :disabled="running || !chain.length">
              {{ running ? '跑中…' : '跑测试' }}
            </button>
          </div>
        </div>

        <div class="desc-row">
          <input v-model="currentDesc" placeholder="场景描述(可选)" class="desc-input" />
        </div>

        <div v-if="!chain.length" class="empty">
          从中间"用例库"点 <b>+</b> 加用例到这里,可拖拽排序
        </div>
        <div v-else class="steps">
          <div v-for="(c, i) in chain" :key="c._uid"
               class="step"
               :class="{ dragging: dragIdx === i }"
               draggable="true"
               @dragstart="onDragStart(i)"
               @dragover.prevent
               @drop="onDrop(i)">
            <span class="step-no">{{ i + 1 }}</span>
            <span class="grip">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 6h.01M8 12h.01M8 18h.01M16 6h.01M16 12h.01M16 18h.01" /></svg>
            </span>
            <span class="tag-method" :class="methodClass(methodOf(c))">{{ methodOf(c) }}</span>
            <span class="step-name">{{ c.name }}</span>
            <button class="icon-btn del" title="移除" @click="removeStep(i)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12" /></svg>
            </button>
          </div>
        </div>
      </template>
    </section>
  </div>

  <!-- 新建场景弹层 -->
  <Modal v-if="showNew" title="新建场景" @close="showNew = false">
    <div class="field">
      <label>场景名</label>
      <input v-model="newName" placeholder="如:下单主流程" @keyup.enter="submitNewScenario" />
    </div>
    <div class="field">
      <label>描述 <span class="opt">(可选)</span></label>
      <input v-model="newDesc" placeholder="一句话说说这个场景干啥" />
    </div>
    <div v-if="newErr" class="form-err">{{ newErr }}</div>
    <template #foot>
      <button class="btn btn-ghost" @click="showNew = false">取消</button>
      <button class="btn btn-primary" @click="submitNewScenario">创建</button>
    </template>
  </Modal>

  <!-- 执行结果弹层 -->
  <Modal v-if="showResult" :title="`执行结果 · ${currentName}`" :max-width="720" @close="showResult = false">
    <div class="verdict">
      <span class="badge" :class="overallPassed ? 'b-pass' : 'b-fail'">
        <span class="dot"></span>{{ overallPassed ? '通过' : '失败' }}
      </span>
      <span class="muted">共 {{ results.length }} 步</span>
    </div>
    <div v-for="(r, i) in results" :key="i" class="run">
      <div class="run-head">
        <span class="badge" :class="r.passed ? 'b-pass' : 'b-fail'">
          <span class="dot"></span>{{ r.passed ? '通过' : '失败' }}
        </span>
        <span class="run-idx">步骤 #{{ i + 1 }}</span>
      </div>
      <div v-if="r.error" class="form-err">{{ r.error }}</div>
      <div v-else class="kv">
        <div><span class="kk">期望状态</span><span class="vv">{{ r.expected_status }}</span></div>
        <div><span class="kk">实际状态</span><span class="vv" :class="{ bad: r.actual_status !== r.expected_status }">{{ r.actual_status }}</span></div>
      </div>
      <div v-if="r.assertions && r.assertions.length" class="asserts">
        <div class="asserts-t">断言 ({{ r.assertions.filter(a => a.passed).length }}/{{ r.assertions.length }} 通过)</div>
        <div v-for="(a, j) in r.assertions" :key="j" class="assert-row" :class="{ fail: !a.passed }">
          <span class="badge" :class="a.passed ? 'b-pass' : 'b-fail'"><span class="dot"></span>{{ a.passed ? 'PASS' : 'FAIL' }}</span>
          <code>{{ fmtJson(a) }}</code>
        </div>
      </div>
    </div>
    <template #foot>
      <button class="btn btn-primary" @click="showResult = false">关闭</button>
    </template>
  </Modal>
</template>

<style scoped>
.state { padding:48px 20px; text-align:center; color:var(--text-muted); font-size:13px; }
.state.err { color:var(--fail-fg); }

/* ===== 三列布局 ===== */
.three-col { display:grid; grid-template-columns:260px 340px 1fr; gap:16px; align-items:stretch; }
.col-left, .col-mid, .col-right { display:flex; flex-direction:column; min-height:520px; }

.panel-head { display:flex; align-items:center; justify-content:space-between; gap:10px;
  padding:14px 18px; border-bottom:1px solid var(--border); font-size:13.5px; font-weight:600; }

.empty { padding:36px 20px; text-align:center; color:var(--text-muted); font-size:12.5px; }
.empty.tall { padding:100px 20px; }

.btn-sm { height:32px; padding:0 12px; font-size:12.5px; }

/* ===== 左:场景列表 ===== */
.sc-list { flex:1; overflow-y:auto; padding:8px; display:flex; flex-direction:column; gap:6px; }
.sc-item { padding:10px 12px; border-radius:8px; cursor:pointer;
  border:1px solid transparent; transition:background .15s, border-color .15s; }
.sc-item:hover { background:var(--surface-2); }
.sc-item.active { background:var(--surface-2); border-color:var(--primary); }
.sc-name { font-size:13px; font-weight:600; color:var(--text); margin-bottom:4px; }
.sc-meta { display:flex; align-items:center; gap:8px; font-size:11.5px; color:var(--text-muted); }
.sc-count { background:var(--surface); border:1px solid var(--border); padding:1px 8px; border-radius:10px; font-weight:500; }
.sc-desc { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; flex:1; }

/* ===== 中:用例库 ===== */
.lib-search { height:30px; padding:0 10px; font-size:12.5px; background:var(--surface-2);
  border:1px solid var(--border); border-radius:6px; color:var(--text); font-family:inherit;
  min-width:0; flex:1; max-width:180px; }
.lib-search:focus { outline:none; border-color:var(--primary); }
.lib-list { flex:1; overflow-y:auto; padding:8px; display:flex; flex-direction:column; gap:4px; }
.lib-item { display:flex; align-items:center; gap:10px; padding:9px 12px;
  border-radius:8px; transition:background .15s; }
.lib-item:hover { background:var(--surface-2); }
.li-name { flex:1; font-size:12.5px; color:var(--text); display:flex; align-items:center; gap:8px;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.li-name .id { color:var(--text-muted); font-family:ui-monospace,Consolas,monospace; font-size:11px;
  background:var(--surface); padding:1px 6px; border-radius:5px; }

/* ===== 右:编辑区 ===== */
.editor-head { flex-wrap:wrap; gap:12px; }
.editor-meta { display:flex; align-items:center; gap:8px; flex:1; min-width:0; }
.editor-name { height:34px; padding:0 12px; font-size:14px; font-weight:600; color:var(--text);
  background:var(--surface-2); border:1px solid var(--border); border-radius:8px;
  flex:1; min-width:100px; font-family:inherit; }
.editor-name:focus { outline:none; border-color:var(--primary); }
.dirty-dot { color:var(--primary); font-size:14px; }
.editor-actions { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.env-sel { height:32px; padding:0 10px; font-size:12.5px; color:var(--text);
  background:var(--surface-2); border:1px solid var(--border); border-radius:6px; font-family:inherit; }
.env-sel:focus { outline:none; border-color:var(--primary); }

.desc-row { padding:12px 18px; border-bottom:1px solid var(--border); }
.desc-input { width:100%; height:32px; padding:0 12px; font-size:12.5px; color:var(--text);
  background:var(--surface-2); border:1px solid var(--border); border-radius:6px; font-family:inherit; }
.desc-input:focus { outline:none; border-color:var(--primary); }

.steps { flex:1; overflow-y:auto; padding:10px 14px; display:flex; flex-direction:column; gap:8px; }
.step { display:flex; align-items:center; gap:12px; padding:10px 14px;
  background:var(--surface-2); border:1px solid var(--border); border-radius:8px;
  cursor:move; transition:background .15s; }
.step:hover { background:var(--surface); }
.step.dragging { opacity:.4; }
.step-no { min-width:26px; text-align:center; font-weight:700; color:var(--text-muted);
  font-family:ui-monospace,Consolas,monospace; font-size:12px; }
.grip { color:var(--text-muted); }
.grip svg { width:14px; height:14px; }
.step-name { flex:1; font-size:12.5px; color:var(--text); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }

/* ===== 通用小按钮 ===== */
.icon-btn { display:inline-flex; align-items:center; justify-content:center;
  width:28px; height:28px; padding:0; background:none; border:none; color:var(--text-muted);
  cursor:pointer; border-radius:4px; transition:color .15s, background .15s; flex:none; }
.icon-btn svg { width:14px; height:14px; }
.icon-btn.add:hover { color:var(--primary); background:var(--surface-2); }
.icon-btn.del:hover { color:var(--fail-fg); background:var(--fail-bg); }

/* ===== 弹层字段 ===== */
.field { margin-bottom:16px; }
.field label { display:block; font-size:12.5px; font-weight:600; margin-bottom:8px; color:var(--text); }
.field label .opt { color:var(--text-muted); font-weight:400; }
.field input { width:100%; height:38px; padding:0 12px; font-size:13px; color:var(--text);
  background:var(--surface-2); border:1px solid var(--border); border-radius:8px; font-family:inherit; }
.field input:focus { outline:none; border-color:var(--primary); }
.form-err { color:var(--fail-fg); font-size:12.5px; background:var(--fail-bg); padding:9px 12px; border-radius:8px; }

/* ===== 结果弹层 ===== */
.verdict { display:flex; align-items:center; gap:12px; margin-bottom:16px; }
.verdict .muted { color:var(--text-muted); font-size:12.5px; }
.run { border:1px solid var(--border); border-radius:12px; padding:14px 16px; margin-bottom:12px; }
.run:last-child { margin-bottom:0; }
.run-head { display:flex; align-items:center; gap:12px; margin-bottom:12px; }
.run-head .run-idx { font-weight:600; font-size:12.5px; }
.kv { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:12px; }
.kv > div { display:flex; flex-direction:column; gap:4px; background:var(--surface-2);
  border:1px solid var(--border); border-radius:8px; padding:10px 12px; }
.kv .kk { font-size:11px; color:var(--text-muted); }
.kv .vv { font-family:ui-monospace,Consolas,monospace; font-weight:700; font-size:15px; }
.kv .vv.bad { color:var(--fail-fg); }
.asserts-t { font-size:12px; color:var(--text-muted); font-weight:600; margin-bottom:8px; }
.assert-row { display:flex; align-items:flex-start; gap:10px; margin-bottom:8px; }
.assert-row code { flex:1; font-family:ui-monospace,Consolas,monospace; font-size:11.5px; color:var(--text-muted);
  background:var(--surface-2); border:1px solid var(--border); border-radius:6px; padding:6px 9px;
  white-space:pre-wrap; word-break:break-all; }

/* ===== 响应式 ===== */
@media (max-width:1200px) {
  .three-col { grid-template-columns:220px 280px 1fr; }
}
@media (max-width:900px) {
  .three-col { grid-template-columns:1fr; }
  .col-left, .col-mid, .col-right { min-height:auto; }
}
</style>
