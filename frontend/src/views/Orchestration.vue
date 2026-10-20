<script setup>
import { useFeedback } from '../composables/feedback'
const { showMessage, confirmAction } = useFeedback()
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useAuthStore } from '../stores/auth'
import { listCases, getCase } from '../api/case'
import { listInterfaces, getInterface } from '../api/interface'
import { useExecutionEnvironment } from '../composables/executionEnvironment'
import EnvironmentSelect from '../components/EnvironmentSelect.vue'
import {
  listScenarios, getScenario, createScenario, updateScenario, deleteScenario, runScenario,
} from '../api/scenario'
import Modal from '../components/Modal.vue'
import ScenarioRunResult from '../components/ScenarioRunResult.vue'
import ScenarioStepEditor from '../components/ScenarioStepEditor.vue'
import ScenarioCasePicker from '../components/ScenarioCasePicker.vue'
import { caseToStep, savedScenarioSteps } from '../utils/scenarioSteps'
import { cloneRequest } from '../utils/requestConfig'

// —— 数据源 ——
const scenarios = ref([])
const cases = ref([])
const interfaces = ref([])
const { envs, selectedEnv, loadEnvironments } = useExecutionEnvironment()
const hasExecutionEnvironment = computed(() => envs.value.some(env => String(env.id) === String(selectedEnv.value || '')))
const executionEnvironmentHint = computed(() => envs.value.length ? '请选择有效的执行环境后再运行。' : '当前项目暂无执行环境，请先在环境管理中创建。')
const auth = useAuthStore()
const debugSession = ref('')
const debugVariables = ref({})
const debugResults = ref({})
const debugMode = ref(false)
function resetDebug() {
  debugSession.value = ''
  debugVariables.value = {}
  debugResults.value = {}
}
function rememberDebug(result) {
  debugSession.value = result.session_id
  debugVariables.value = result.variables || {}
  debugResults.value = { ...debugResults.value, [result.step_id]:result }
}
const loading = ref(true)
const error = ref('')

// —— 当前选中的场景 ——
const currentId = ref(null)              // null=未选;数字=编辑中
const currentName = ref('')
const currentDesc = ref('')
const chain = ref([])                    // [{case obj}] 有序
const editingStep = ref(null)
const editorRevision = ref(0)
const showCasePicker = ref(false)
const showMore = ref(false)
const saving = ref(false)
const refreshing = ref(false)
// 快照:加载/保存时打一份,dirty = 当前 vs 快照 (避免用 watch 追踪的时序 bug)
const originalSnapshot = ref(null)
let selectionVersion = 0
watch(() => [auth.token, auth.currentProjectId, currentId.value, selectedEnv.value], () => {
  resetDebug()
  editingStep.value = null
}, { flush:'sync' })

const dirty = computed(() => {
  if (!currentId.value || !originalSnapshot.value) return false
  const o = originalSnapshot.value
  if (currentName.value !== o.name) return true
  if ((currentDesc.value || '') !== (o.description || '')) return true
  return JSON.stringify(chain.value) !== JSON.stringify(o.steps)
})

function snapshotCurrent() {
  originalSnapshot.value = {
    name: currentName.value,
    description: currentDesc.value || '',
    steps: cloneRequest(chain.value),
  }
}

// —— 场景导航 ——
const scenarioSearch = ref('')
const filteredScenarios = computed(() => {
  const q = scenarioSearch.value.trim().toLowerCase()
  return scenarios.value.filter(sc => `${sc.name} ${sc.description || ''}`.toLowerCase().includes(q))
})

// —— 拖拽 ——
const dragIdx = ref(null)

// —— 跑测试 ——
const running = ref(false)
const showResult = ref(false)
const results = ref([])

// —— 新建场景弹层 ——
const showNew = ref(false)
const newName = ref('')
const newDesc = ref('')
const newErr = ref('')

// —— 派生 ——
const ifaceMap = computed(() => {
  const m = {}
  for (const it of interfaces.value) m[it.id] = it
  return m
})
function methodOf(c) { return (c?.method || ifaceMap.value[c?.interface_id]?.method || 'GET').toUpperCase() }
function methodClass(m) { return 'm-' + (m || 'get').toLowerCase() }

// —— 加载全量 ——
async function load() {
  loading.value = true
  error.value = ''
  try {
    const [scs, cs, ifs] = await Promise.all([
      listScenarios(), listCases(), listInterfaces(), loadEnvironments(),
    ])
    scenarios.value = scs
    cases.value = cs
    interfaces.value = ifs
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

// —— 场景操作 ——
async function selectScenario(sc) {
  if (saving.value || running.value || refreshing.value) return
  if (dirty.value && !(await confirmAction('当前场景有未保存改动,切换会丢弃。继续?'))) return
  const version = ++selectionVersion
  try {
    // 拉全量数据(list 接口跟 get 应该一致,但保险起见)
    const full = await getScenario(sc.id)
    if (version !== selectionVersion) return
    currentId.value = full.id
    currentName.value = full.name
    currentDesc.value = full.description || ''
    chain.value = savedScenarioSteps(full, cases.value, interfaces.value)
    editingStep.value = null
    showCasePicker.value = false
    showMore.value = false
    snapshotCurrent()
  } catch (e) {
    showMessage(e.message || '加载场景失败', 'error')
  }
}

function openNewScenario() {
  if (saving.value || running.value || refreshing.value) return
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
  if (!currentId.value || saving.value || running.value || refreshing.value) return false
  saving.value = true
  try {
    const payload = {
      name: currentName.value.trim() || '未命名',
      description: currentDesc.value.trim() || null,
      steps: cloneRequest(chain.value),
    }
    const sc = await updateScenario(currentId.value, payload)
    // 更新列表里的对应项
    const idx = scenarios.value.findIndex(s => s.id === sc.id)
    if (idx !== -1) scenarios.value[idx] = sc
    chain.value = savedScenarioSteps(sc, cases.value, interfaces.value)
    snapshotCurrent()
    return true
  } catch (e) {
    showMessage(e.message || '保存失败', 'error')
    return false
  } finally {
    saving.value = false
  }
}

async function deleteCurrent() {
  showMore.value = false
  if (saving.value || running.value || refreshing.value) return
  if (!currentId.value) return
  if (!(await confirmAction(`确认删除场景「${currentName.value}」? (关联的用例不会删)`))) return
  try {
    await deleteScenario(currentId.value)
    scenarios.value = scenarios.value.filter(s => s.id !== currentId.value)
    clearEditor()
  } catch (e) {
    showMessage(e.message || '删除失败', 'error')
  }
}

function clearEditor() {
  selectionVersion += 1
  currentId.value = null
  currentName.value = ''
  currentDesc.value = ''
  chain.value = []
  editingStep.value = null
  showCasePicker.value = false
  showMore.value = false
  originalSnapshot.value = null
}

// —— chain 操作 ——
function addToChain(c) {
  if (saving.value || running.value || refreshing.value) return
  if (!currentId.value) { showMessage('请先选择或新建一个场景', 'error'); return }
  const step = caseToStep(c, ifaceMap.value[c.interface_id])
  chain.value.push(step)
}
function openCasePicker() {
  if (!currentId.value || saving.value || running.value || refreshing.value) return
  showCasePicker.value = true
}
function addCases(items) {
  if (saving.value || running.value || refreshing.value) return
  if (chain.value.length + items.length > 1000) { showMessage('每个场景最多添加 1000 个步骤', 'error'); return }
  for (const item of items) addToChain(item)
  showCasePicker.value = false
}
function removeStep(i) {
  if (saving.value || running.value || refreshing.value) return
  chain.value.splice(i, 1)
}
function onDragStart(i) { if (!saving.value && !running.value && !refreshing.value) dragIdx.value = i }
function moveStep(i, offset) {
  if (saving.value || running.value || refreshing.value) return
  const target = i + offset
  if (target < 0 || target >= chain.value.length) return
  const [step] = chain.value.splice(i, 1)
  chain.value.splice(target, 0, step)
}
function onDrop(i) {
  if (saving.value || running.value || refreshing.value) return
  const from = dragIdx.value
  if (from === null || from === i) { dragIdx.value = null; return }
  const [moved] = chain.value.splice(from, 1)
  chain.value.splice(i, 0, moved)
  dragIdx.value = null
}

function editStep(step, debug = false) {
  if (!step || saving.value || running.value || refreshing.value) return
  editingStep.value = cloneRequest(step)
  debugMode.value = debug
}
function applyStep(step) {
  const index = chain.value.findIndex(item => item.step_id === step.step_id)
  if (index >= 0) chain.value[index] = cloneRequest(step)
  editingStep.value = null
}
async function reapplyTemplate(step) {
  if (!step?.source_case_id || saving.value || running.value || refreshing.value) return
  if (!(await confirmAction('重新应用模板会覆盖当前步骤的修改，其他步骤不受影响。继续？'))) return
  refreshing.value = true
  try {
    const testCase = await getCase(step.source_case_id)
    const request = await getInterface(testCase.interface_id)
    // Keep the fresh template in the modal draft until the user applies it.
    editingStep.value = caseToStep(testCase, request, step.step_id)
    editorRevision.value += 1
    showMessage('已载入最新模板，应用后请保存场景', 'success')
  } catch (e) {
    showMessage(e.message || '来源用例或接口已不可用，当前步骤配置已保留', 'error')
  } finally { refreshing.value = false }
}

// —— 跑 ——
async function onRun() {
  if (!hasExecutionEnvironment.value) { showMessage(executionEnvironmentHint.value, 'error'); return }
  if (!currentId.value || saving.value || running.value || refreshing.value) return
  if (dirty.value) {
    if (!(await confirmAction('当前场景有未保存修改，保存后执行？'))) return
    if (!(await saveCurrent())) return
  }
  if (!hasExecutionEnvironment.value) { showMessage(executionEnvironmentHint.value, 'error'); return }
  running.value = true
  try {
    const data = await runScenario(currentId.value, selectedEnv.value || undefined)
    results.value = Array.isArray(data) ? data : [data]
    showResult.value = true
  } catch (e) {
    showMessage(e.message || '执行失败', 'error')
  } finally {
    running.value = false
  }
}

onMounted(load)
</script>

<template>
  <div v-if="loading" class="state">加载中…</div>
  <div v-else-if="error" class="state err">{{ error }} <button class="btn btn-ghost" @click="load">重试</button></div>
  <div v-else class="scenario-layout">
    <aside class="scenario-nav panel" aria-label="场景导航">
      <div class="panel-head"><span>场景 <small>{{ scenarios.length }}</small></span><button class="icon-btn" aria-label="新建场景" title="新建场景" :disabled="saving || running || refreshing" @click="openNewScenario">＋</button></div>
      <div class="nav-search"><input v-model="scenarioSearch" aria-label="搜索场景" placeholder="搜索场景…" /></div>
      <div class="sc-list">
        <p v-if="!scenarios.length" class="nav-empty">还没有场景，点击下方新建。</p>
        <p v-else-if="!filteredScenarios.length" class="nav-empty">没有匹配的场景</p>
        <button v-for="sc in filteredScenarios" :key="sc.id" type="button" class="sc-item" :class="{ active:sc.id === currentId }" :aria-current="sc.id === currentId ? 'true' : undefined" :disabled="saving || running || refreshing" @click="selectScenario(sc)">
          <span class="sc-name" :title="sc.name">{{ sc.name }}</span><span class="sc-meta">{{ sc.id === currentId ? chain.length : (sc.steps || sc.case_ids || []).length }} 个步骤</span>
        </button>
      </div>
      <div class="nav-footer"><button class="btn btn-ghost" :disabled="saving || running || refreshing" @click="openNewScenario">＋ 新建场景</button></div>
    </aside>

    <section class="scenario-editor panel" aria-label="场景步骤">
      <div v-if="!currentId" class="editor-empty"><strong>选择一个场景开始编排</strong><p>按业务顺序添加用例，组成完整的接口测试链路。</p><button class="btn btn-primary btn-sm" @click="openNewScenario">新建场景</button></div>
      <template v-else>
        <div class="editor-head">
          <div class="editor-meta"><input v-model="currentName" class="editor-name" aria-label="场景名称" placeholder="场景名称" maxlength="100" :disabled="saving || running || refreshing" /><span v-if="dirty" class="dirty-label">未保存</span></div>
          <div class="editor-actions">
            <EnvironmentSelect v-model="selectedEnv" :environments="envs" required placeholder="请选择执行环境" title="执行环境" />
            <button class="btn btn-ghost btn-sm" @click="saveCurrent" :disabled="!dirty || saving || running || refreshing">{{ saving ? '保存中…' : '保存' }}</button>
            <button class="btn btn-primary btn-sm" @click="onRun" :disabled="running || saving || refreshing || !chain.length || !hasExecutionEnvironment" :title="!hasExecutionEnvironment ? executionEnvironmentHint : '运行场景'">{{ running ? '执行中…' : '运行场景' }}</button>
            <div class="more-actions" @focusout="event => { if (!event.currentTarget.contains(event.relatedTarget)) showMore = false }" @keydown.esc="showMore = false">
              <button class="icon-btn" type="button" aria-label="更多场景操作" :aria-expanded="showMore" aria-haspopup="menu" :disabled="saving || running || refreshing" @click="showMore = !showMore">⋯</button>
              <div v-if="showMore" class="more-menu" role="menu"><button role="menuitem" type="button" @click="deleteCurrent">删除场景</button></div>
            </div>
          </div>
          <input v-model="currentDesc" class="desc-input" aria-label="场景简介" placeholder="添加场景简介（可选）" maxlength="500" :disabled="saving || running || refreshing" />
        </div>
        <p v-if="!hasExecutionEnvironment" class="execution-environment-hint" role="status">{{ executionEnvironmentHint }} <RouterLink v-if="!envs.length" to="/environments">前往环境管理</RouterLink></p>
        <div class="flow-heading"><strong>执行步骤 <span>{{ chain.length }}</span></strong><span>按顺序执行 · 可拖拽调整</span></div>
        <div v-if="!chain.length" class="canvas-empty"><strong>从用例库添加第一个步骤</strong><p>每个步骤都可以单独修改请求、期望状态码和断言。</p><button class="btn btn-primary btn-sm" @click="openCasePicker">＋ 从用例库添加步骤</button></div>
        <template v-else>
          <div class="steps" role="list" aria-label="按执行顺序排列的步骤">
            <div v-for="(c, i) in chain" :key="c.step_id" class="step" role="listitem" :class="{ dragging:dragIdx === i, invalid:!!c.missing_reason }" @dblclick="editStep(c)" @dragover.prevent @drop.prevent="onDrop(i)">
              <button class="grip" type="button" :aria-label="`调整步骤 ${i + 1} 顺序，方向键上下移动`" title="拖拽排序，也可聚焦后使用上下方向键" :disabled="saving || running || refreshing" :draggable="!saving && !running && !refreshing" @dragstart="onDragStart(i)" @dragend="dragIdx = null" @keydown.up.prevent="moveStep(i, -1)" @keydown.down.prevent="moveStep(i, 1)"><svg viewBox="0 0 24 24" fill="currentColor"><circle v-for="(point, index) in [[8,6],[8,12],[8,18],[16,6],[16,12],[16,18]]" :key="index" :cx="point[0]" :cy="point[1]" r="1.5" /></svg></button>
              <span class="step-no">{{ i + 1 }}</span>
              <div class="step-copy"><strong class="step-name" :title="c.name">{{ c.name }}</strong><span class="step-request"><span class="tag-method" :class="methodClass(methodOf(c))">{{ c.method || (c.missing_reason ? '—' : methodOf(c)) }}</span><code :title="c.url">{{ c.url || '请求配置不可用' }}</code></span><span v-if="c.missing_reason" class="step-error">{{ c.missing_reason }}</span></div>
              <span class="step-status">期望 <b>{{ c.expected_status || '—' }}</b></span>
              <button class="step-edit step-debug" :disabled="!!c.missing_reason || saving || running || refreshing" :aria-label="`调试步骤 ${i + 1}：${c.name}`" @click="editStep(c, true)">调试</button>
              <button class="step-edit" :disabled="saving || running || refreshing" :aria-label="`编辑步骤 ${i + 1}：${c.name}`" @click="editStep(c)">编辑</button>
              <button class="icon-btn del" :aria-label="`移除步骤 ${i + 1}：${c.name}`" title="移除步骤" :disabled="saving || running || refreshing" @click="removeStep(i)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M6 7h12M9 7V4h6v3M8 7l1 13h6l1-13" /></svg></button>
            </div>
          </div>
          <div class="add-step-row"><button type="button" class="add-step" :disabled="saving || running || refreshing" @click="openCasePicker">＋ 从用例库添加步骤</button><span>添加后可独立编辑</span></div>
        </template>
      </template>
    </section>
  </div>

  <ScenarioCasePicker v-if="showCasePicker" :cases="cases" :interfaces="interfaces" :remaining="1000 - chain.length" @add="addCases" @close="showCasePicker = false" />
  <ScenarioStepEditor v-if="editingStep" :key="`${editingStep.step_id}-${editorRevision}`" :step="editingStep" :busy="refreshing" :scenario-id="currentId" :env-id="selectedEnv" :environment-name="envs.find(item => String(item.id) === String(selectedEnv))?.name || ''" :debug-mode="debugMode" :session-id="debugSession" :variables="debugVariables" :debug-result="debugResults[editingStep.step_id]" @debug="rememberDebug" @reset-debug="resetDebug" @reapply="reapplyTemplate(editingStep)" @apply="applyStep" @close="editingStep = null" />

  <Modal v-if="showNew" title="新建场景" @close="showNew = false">
    <div class="field"><label for="new-scene-name">场景名称</label><input id="new-scene-name" v-model="newName" maxlength="100" placeholder="如：订单核心链路" @keyup.enter="submitNewScenario" /></div>
    <div class="field"><label for="new-scene-desc">简介 <span class="opt">（可选）</span></label><input id="new-scene-desc" v-model="newDesc" maxlength="500" placeholder="描述需要验证的业务流程" /></div>
    <div v-if="newErr" class="form-err">{{ newErr }}</div>
    <template #foot><button class="btn btn-ghost" @click="showNew = false">取消</button><button class="btn btn-primary" @click="submitNewScenario">创建</button></template>
  </Modal>
  <Modal v-if="showResult" :title="`执行结果 · ${currentName}`" :max-width="720" @close="showResult = false">
    <ScenarioRunResult :results="results" />
    <template #foot><button class="btn btn-primary" @click="showResult = false">关闭</button></template>
  </Modal>
</template>

<style scoped>
.execution-environment-hint{margin:0;padding:10px 18px;color:var(--text-muted);font-size:12px;line-height:1.6}
.scenario-layout{display:grid;grid-template-columns:220px minmax(0,1fr);gap:18px;align-items:stretch}
.scenario-nav,.scenario-editor{display:flex;flex-direction:column;min-width:0;min-height:520px}
.panel-head{display:flex;align-items:center;justify-content:space-between;padding:14px 16px 10px;font-size:14px;font-weight:600}
.panel-head small{margin-left:6px;font-size:11px;font-weight:400;color:var(--text-muted)}
.nav-search{padding:0 12px 12px}
.nav-search input{box-sizing:border-box;width:100%;height:34px;border:1px solid var(--border);border-radius:7px;background:var(--surface-2);color:var(--text);padding:0 10px;font:inherit;font-size:12px}
.sc-list{display:flex;flex-direction:column;gap:5px;flex:1;max-height:65vh;overflow:auto;scrollbar-width:none;padding:0 8px 8px}
.sc-list::-webkit-scrollbar{display:none}
.sc-item{text-align:left;border:1px solid transparent;border-radius:8px;background:transparent;padding:12px;color:var(--text);font:inherit;cursor:pointer}
.sc-item:hover{background:var(--surface-2)}
.sc-item.active{background:var(--surface-2);border-color:var(--border);box-shadow:inset 3px 0 var(--primary)}
.sc-name{display:block;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;font-size:13px;font-weight:600;margin-bottom:5px}
.sc-item.active .sc-name{color:var(--primary)}
.sc-meta{color:var(--text-muted);font-size:11px}
.nav-empty{padding:20px 8px;text-align:center;color:var(--text-muted);font-size:12px;line-height:1.7}
.nav-footer{padding:12px;border-top:1px solid var(--border)}
.nav-footer .btn{width:100%;font-size:12px;height:34px}
.editor-head{display:flex;align-items:center;flex-wrap:wrap;gap:12px;padding:18px 20px;border-bottom:1px solid var(--border)}
.editor-meta{display:flex;align-items:center;gap:8px;flex:1;min-width:180px}
.editor-name{box-sizing:border-box;min-width:0;width:100%;height:34px;background:transparent;border:1px solid transparent;border-radius:6px;padding:0 6px;font-family:inherit;font-size:17px;font-weight:700;color:var(--text)}
.editor-name:hover{border-color:var(--border)}
.editor-name:focus{background:var(--surface-2)}
.dirty-label{flex:none;font-size:10px;color:var(--primary);white-space:nowrap}
.editor-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.editor-actions :deep(.env-select){max-width:220px}
.desc-input{box-sizing:border-box;width:100%;height:28px;border:1px solid transparent;border-radius:5px;padding:0 6px;background:transparent;color:var(--text-muted);font:inherit;font-size:12px}
.desc-input:hover{border-color:var(--border)}
.desc-input:focus{color:var(--text);background:var(--surface-2)}
.btn-sm{height:32px;padding:0 12px;font-size:12px}
.more-actions{position:relative}
.more-menu{position:absolute;right:0;top:calc(100% + 5px);z-index:10;min-width:120px;padding:5px;background:var(--surface);border:1px solid var(--border);border-radius:7px;box-shadow:var(--shadow-lg)}
.more-menu button{width:100%;border:0;border-radius:4px;background:transparent;color:var(--fail-fg);padding:9px;text-align:left;font:inherit;font-size:12px;cursor:pointer}
.more-menu button:hover{background:var(--fail-bg)}
.flow-heading{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:17px 20px 12px;font-size:12px}
.flow-heading strong{font-size:13px;font-weight:600}
.flow-heading strong span{margin-left:5px;font-size:11px;font-weight:400;color:var(--text-muted)}
.flow-heading>span{color:var(--text-muted);font-size:11px}
.steps{padding:0 20px;display:flex;flex-direction:column;gap:8px}
.step{display:flex;align-items:center;gap:10px;min-width:0;min-height:66px;box-sizing:border-box;padding:10px 12px 10px 6px;border:1px solid var(--border);border-radius:9px;background:var(--surface);transition:background .15s}
.step:hover{background:var(--surface-2)}
.step.dragging{opacity:.4}
.step.invalid{border-color:var(--fail-fg)}
.step-no{flex:none;min-width:22px;color:var(--text-muted);font-size:12px;text-align:center;font-variant-numeric:tabular-nums}
.grip{display:grid;place-items:center;flex:none;width:20px;height:28px;padding:0;border:0;background:transparent;color:var(--text-muted);cursor:grab}
.grip:active{cursor:grabbing}
.grip svg{width:14px;height:16px}
.step-copy{flex:1;min-width:0}
.step-name{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text);font-size:13px;font-weight:600;line-height:1.6}
.step-request{display:flex;align-items:center;gap:8px;margin-top:4px;min-width:0}
.step-request code{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--text-muted);font:11px/1.4 ui-monospace,Consolas,monospace}
.step-request .tag-method{flex:none;min-width:35px;font-size:9px;text-align:center;padding:1px 5px;line-height:1.4}
.step-status{display:flex;align-items:center;gap:6px;flex:none;font-size:11px;color:var(--text-muted);margin:0 8px}
.step-status b{font-size:12px;color:var(--text);font-weight:600;font-variant-numeric:tabular-nums}
.step-edit{flex:none;border:0;background:transparent;color:var(--primary);font:inherit;font-size:12px;padding:6px;cursor:pointer}
.icon-btn{display:inline-flex;align-items:center;justify-content:center;flex:none;width:28px;height:28px;border:0;border-radius:5px;background:transparent;color:var(--text-muted);font:inherit;font-size:21px;cursor:pointer}
.icon-btn svg{width:16px;height:16px}
.icon-btn:hover{background:var(--surface-2);color:var(--primary)}
.icon-btn.del:hover{color:var(--fail-fg);background:var(--fail-bg)}
.step-error{display:block;margin-top:4px;color:var(--fail-fg);font-size:11px;overflow-wrap:anywhere}
.add-step-row{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:12px 20px 20px;padding:0 4px}
.add-step{border:0;background:transparent;color:var(--primary);padding:10px 0;font:inherit;font-size:12px;cursor:pointer}
.add-step-row>span{font-size:11px;color:var(--text-muted)}
.editor-empty,.canvas-empty{text-align:center;padding:90px 20px;color:var(--text-muted)}
.canvas-empty{padding:60px 20px}
.editor-empty strong,.canvas-empty strong{color:var(--text);font-size:14px}
.editor-empty p,.canvas-empty p{font-size:12px;line-height:1.8;margin:10px 0 20px}
.state{padding:48px 20px;text-align:center;color:var(--text-muted);font-size:13px}
.state.err{color:var(--fail-fg)}
.field{margin-bottom:16px}
.field label{display:block;margin-bottom:8px;color:var(--text);font-size:13px;font-weight:600}
.field .opt{font-weight:400;color:var(--text-muted)}
.field input{box-sizing:border-box;width:100%;height:38px;padding:0 12px;border:1px solid var(--border);border-radius:7px;background:var(--surface-2);color:var(--text);font:inherit;font-size:13px}
.form-err{padding:10px;background:var(--fail-bg);color:var(--fail-fg);font-size:12px;border-radius:6px}
button:focus-visible,input:focus-visible{outline:2px solid var(--primary);outline-offset:2px}
button:disabled{opacity:.5;cursor:default}
@media(max-width:1100px){.scenario-layout{grid-template-columns:200px minmax(0,1fr);gap:14px}
.editor-actions{width:100%}
.editor-meta{min-width:0}
.editor-head{gap:8px}
.desc-input{order:1}
.editor-actions{order:2}
.editor-actions :deep(.env-select){margin-right:auto}
.steps{padding:0 14px}
.flow-heading{padding-left:14px;padding-right:14px}
.add-step-row{margin-left:14px;margin-right:14px}
}
@media(max-width:760px){.scenario-layout{grid-template-columns:minmax(0,1fr)}
.scenario-nav{min-height:auto}
.sc-list{max-height:180px}
.nav-footer{padding:8px 12px}
.scenario-editor{min-height:400px}
.editor-head{padding:14px}
.step{gap:5px;padding-right:8px}
.step-status{margin:0 2px;font-size:10px;gap:3px}
.step-status b{font-size:11px}
.step-name{font-size:12px}
.step-no{min-width:16px;font-size:11px}
.step-edit{padding:5px;font-size:11px}
.icon-btn.del{width:24px}
.grip{width:16px}
.flow-heading>span,.add-step-row>span{display:none}
.editor-actions{gap:6px}
.editor-actions :deep(.env-select){max-width:100%;flex:1;min-width:130px}
.editor-actions .btn{padding:0 9px;font-size:11px}
.more-actions .icon-btn{width:24px}
}
</style>
