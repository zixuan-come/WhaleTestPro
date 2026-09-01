<script setup>
import { useFeedback } from '../composables/feedback'
const { showMessage, confirmAction } = useFeedback()
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { listCases, createCase, updateCase, deleteCase, runCase } from '../api/case'
import { listInterfaces } from '../api/interface'
import { listEnvironments } from '../api/environment'
import { useAuthStore } from '../stores/auth'
import Modal from '../components/Modal.vue'

const auth = useAuthStore()
const router = useRouter()

const items = ref([])
const interfaces = ref([])
const envs = ref([])
const loading = ref(true)
const error = ref('')

const selectedEnv = ref('')        // 跑测试用的环境 id(空=不带 env)
const runningId = ref(null)        // 正在跑的用例 id

// 结果弹层
const showResult = ref(false)
const resultCase = ref(null)
const resultData = ref(null)

// 新建/编辑弹层
const showModal = ref(false)
const editingId = ref(null)
const saving = ref(false)
const formErr = ref('')
const showAdvanced = ref(false)
const form = reactive({
  name: '', interface_id: '', expected_status: 200, retries: 0, tags: '',
  extract_rules: '', assertions: '', setup_sql: '', teardown_sql: '', datasets: '',
})

const total = computed(() => items.value.length)

// 接口 id → 名称/方法,列表里显示更友好
const ifaceMap = computed(() => {
  const m = {}
  for (const it of interfaces.value) m[it.id] = it
  return m
})
const selectedInterface = computed(() => ifaceMap.value[form.interface_id] || null)

function jsonFieldHasValue(text) {
  const raw = (text || '').trim()
  if (!raw) return false
  try {
    const value = JSON.parse(raw)
    if (Array.isArray(value)) return value.length > 0
    if (value && typeof value === 'object') return Object.keys(value).length > 0
    return value != null
  } catch {
    return true
  }
}

const advancedConfigCount = computed(() => [
  form.assertions,
  form.extract_rules,
  form.setup_sql,
  form.teardown_sql,
  form.datasets,
].filter(jsonFieldHasValue).length)

function hasAdvancedConfig(testCase) {
  return [
    testCase.assertions,
    testCase.extract_rules,
    testCase.setup_sql,
    testCase.teardown_sql,
    testCase.datasets,
  ].some(value => {
    if (Array.isArray(value)) return value.length > 0
    if (value && typeof value === 'object') return Object.keys(value).length > 0
    return value != null && value !== ''
  })
}

function ifaceLabel(id) {
  const it = ifaceMap.value[id]
  return it ? `${(it.method || 'GET').toUpperCase()} ${it.name}` : `#${id}`
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [cs, ifs, es] = await Promise.all([listCases(), listInterfaces(), listEnvironments()])
    items.value = cs
    interfaces.value = ifs
    envs.value = es

    // 恢复上次选的环境:如果记忆的 envId 还存在于当前项目的环境列表里,就选它;否则清空
    const remembered = auth.getPreferredEnv(auth.currentProjectId)
    if (remembered && es.some(e => String(e.id) === String(remembered))) {
      selectedEnv.value = String(remembered)
    } else if (remembered) {
      // 记忆的环境被删了 → 清掉这条脏数据
      auth.setPreferredEnv(auth.currentProjectId, null)
      selectedEnv.value = ''
    }
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

// 用户手动切换 → 立刻持久化到当前项目名下
watch(selectedEnv, (v) => {
  auth.setPreferredEnv(auth.currentProjectId, v || null)
})

function openCreate() {
  editingId.value = null
  form.name = ''
  form.interface_id = ''
  form.expected_status = 200
  form.retries = 0
  form.tags = ''
  form.extract_rules = ''
  form.assertions = ''
  form.setup_sql = ''
  form.teardown_sql = ''
  form.datasets = ''
  showAdvanced.value = false
  formErr.value = ''
  showModal.value = true
}

function formatJsonField(value) {
  return value == null ? '' : JSON.stringify(value, null, 2)
}

function openEdit(testCase) {
  editingId.value = testCase.id
  form.name = testCase.name
  form.interface_id = testCase.interface_id
  form.expected_status = testCase.expected_status
  form.retries = testCase.retries || 0
  form.tags = (testCase.tags || []).join(', ')
  form.extract_rules = formatJsonField(testCase.extract_rules)
  form.assertions = formatJsonField(testCase.assertions)
  form.setup_sql = formatJsonField(testCase.setup_sql)
  form.teardown_sql = formatJsonField(testCase.teardown_sql)
  form.datasets = formatJsonField(testCase.datasets)
  showAdvanced.value = hasAdvancedConfig(testCase)
  formErr.value = ''
  showModal.value = true
}

function closeModal() {
  if (saving.value) return
  showModal.value = false
}

function goToInterfaces() {
  if (saving.value) return
  showModal.value = false
  router.push({ name: 'interfaces' })
}

function parseJsonField(text, label) {
  const s = (text || '').trim()
  if (!s) return null
  try {
    return JSON.parse(s)
  } catch {
    throw new Error(`${label} 不是合法 JSON`)
  }
}

async function save() {
  formErr.value = ''
  if (!form.name.trim()) { formErr.value = '请填写用例名称'; return }
  if (!form.interface_id) { formErr.value = '请选择关联接口'; return }

  let extract_rules, assertions, setup_sql, teardown_sql, datasets
  try {
    extract_rules = parseJsonField(form.extract_rules, '提取规则')
    assertions = parseJsonField(form.assertions, '断言')
    setup_sql = parseJsonField(form.setup_sql, '前置 SQL')
    teardown_sql = parseJsonField(form.teardown_sql, '后置 SQL')
    datasets = parseJsonField(form.datasets, '数据集')
  } catch (e) {
    showAdvanced.value = true
    formErr.value = e.message
    return
  }

  const tags = form.tags.trim() ? form.tags.split(',').map(t => t.trim()).filter(Boolean) : null

  saving.value = true
  try {
    const payload = {
      name: form.name.trim(),
      interface_id: Number(form.interface_id),
      expected_status: Number(form.expected_status),
      retries: Number(form.retries) || 0,
      tags,
      extract_rules, assertions, setup_sql, teardown_sql, datasets,
    }

    if (editingId.value == null) {
      await createCase(payload)
    } else {
      await updateCase(editingId.value, payload)
    }
    showModal.value = false
    await load()
  } catch (e) {
    formErr.value = e.message || '保存失败'
  } finally {
    saving.value = false
  }
}

async function onRun(c) {
  runningId.value = c.id
  try {
    const data = await runCase(c.id, selectedEnv.value || undefined)
    resultCase.value = c
    resultData.value = data
    showResult.value = true
  } catch (e) {
    showMessage(e.message || '执行失败', 'error')
  } finally {
    runningId.value = null
  }
}

async function onDelete(c) {
  if (!(await confirmAction(`确认删除用例「${c.name}」?`))) return
  try {
    await deleteCase(c.id)
    items.value = items.value.filter(i => i.id !== c.id)
  } catch (e) {
    showMessage(e.message || '删除失败', 'error')
  }
}

// 结果归一化:单次是 dict,数据驱动是数组 → 统一成数组
const runs = computed(() => {
  const d = resultData.value
  if (!d) return []
  return Array.isArray(d) ? d : [d]
})
const overallPassed = computed(() => runs.value.length > 0 && runs.value.every(r => r.passed))

function fmtJson(v) { return JSON.stringify(v, null, 2) }

onMounted(load)
</script>

<template>
  <div class="cards">
    <div class="card"><div class="k">用例总数</div><div class="v pri">{{ total }}</div></div>
    <div class="card"><div class="k">关联接口</div><div class="v">{{ interfaces.length }}</div></div>
    <div class="card"><div class="k">可用环境</div><div class="v">{{ envs.length }}</div></div>
  </div>

  <div class="panel">
    <div class="panel-head">
      测试用例
      <div class="head-actions">
        <select v-model="selectedEnv" class="env-sel" title="跑测试时使用的环境">
          <option value="">不指定环境</option>
          <option v-for="e in envs" :key="e.id" :value="e.id">环境:{{ e.name }}</option>
        </select>
        <button class="btn btn-primary" @click="openCreate">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14" /></svg>
          新建用例
        </button>
      </div>
    </div>

    <div v-if="loading" class="state">加载中…</div>
    <div v-else-if="error" class="state err">
      {{ error }}
      <button class="btn btn-ghost retry" @click="load">重试</button>
    </div>
    <div v-else-if="!items.length && !interfaces.length" class="state">
      <div class="state-title">还没有可关联的接口</div>
      <div class="state-copy">测试用例需要复用接口的请求方法、URL 和参数，请先创建接口。</div>
      <button class="btn btn-primary state-action" @click="goToInterfaces">前往接口管理</button>
    </div>
    <div v-else-if="!items.length" class="state">暂无用例，点右上角「新建用例」创建</div>

    <template v-else>
      <div class="row head">
        <span class="c-name">用例</span>
        <span class="c-iface">关联接口</span>
        <span class="c-exp">期望状态</span>
        <span class="c-tags">标签</span>
        <span class="c-act">操作</span>
      </div>
      <div v-for="(c, i) in items" :key="c.id" class="row">
        <span class="c-name"><span class="id">#{{ i + 1 }}</span>{{ c.name }}</span>
        <span class="c-iface" :title="ifaceLabel(c.interface_id)">{{ ifaceLabel(c.interface_id) }}</span>
        <span class="c-exp">{{ c.expected_status }}</span>
        <span class="c-tags">
          <span v-for="t in (c.tags || [])" :key="t" class="tag">{{ t }}</span>
          <span v-if="!(c.tags && c.tags.length)" class="muted">—</span>
        </span>
        <span class="c-act">
          <button class="icon-btn run" title="跑测试" :disabled="runningId === c.id" @click="onRun(c)">
            <svg v-if="runningId !== c.id" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 4l14 8-14 8V4Z" /></svg>
            <span v-else class="spin"></span>
          </button>
          <button class="icon-btn edit" title="编辑" @click="openEdit(c)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" /></svg>
          </button>
          <button class="icon-btn del" title="删除" @click="onDelete(c)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" /></svg>
          </button>
        </span>
      </div>
    </template>
  </div>

  <!-- 新建/编辑用例弹层 -->
  <Modal v-if="showModal" :title="editingId == null ? '新建测试用例' : '编辑测试用例'" :max-width="620" :busy="saving" @close="closeModal">
    <div class="field">
      <label>用例名称</label>
      <input v-model="form.name" placeholder="如:下单成功返回 200" />
    </div>
    <div class="field interface-field">
      <label for="case-interface">关联接口 <span class="opt">(必选，复用接口请求配置)</span></label>
      <template v-if="interfaces.length">
        <select id="case-interface" v-model="form.interface_id">
          <option value="" disabled>请选择当前项目的接口</option>
          <option v-for="it in interfaces" :key="it.id" :value="it.id">
            {{ (it.method || 'GET').toUpperCase() }} · {{ it.name }} · {{ it.url }}
          </option>
        </select>
        <div v-if="selectedInterface" class="interface-preview" aria-live="polite">
          <span class="method-pill">{{ (selectedInterface.method || 'GET').toUpperCase() }}</span>
          <div class="preview-copy">
            <strong class="preview-name">{{ selectedInterface.name }}</strong>
            <code class="preview-url">{{ selectedInterface.url }}</code>
          </div>
        </div>
        <div v-else-if="form.interface_id" class="orphan-warning" role="alert">
          原关联接口已不存在，请重新选择一个接口。
        </div>
      </template>
      <div v-else class="interface-empty">
        <div>
          <strong>当前项目还没有接口</strong>
          <p>请先创建接口，再回来编写测试用例。接口的 Method、URL、Header、Query 和 Body 会被用例直接复用。</p>
        </div>
        <button type="button" class="btn btn-primary" @click="goToInterfaces">前往接口管理</button>
      </div>
    </div>
    <div class="grid2">
      <div class="field">
        <label for="case-expected-status">期望状态码</label>
        <input id="case-expected-status" v-model.number="form.expected_status" type="number" />
      </div>
      <div class="field">
        <label for="case-retries">失败重试</label>
        <input id="case-retries" v-model.number="form.retries" type="number" min="0" />
      </div>
    </div>
    <div class="field">
      <label>标签 <span class="opt">(逗号分隔,可选)</span></label>
      <input v-model="form.tags" placeholder="smoke, order" />
    </div>
    <button
      type="button"
      class="advanced-toggle"
      :aria-expanded="showAdvanced"
      aria-controls="case-advanced-settings"
      @click="showAdvanced = !showAdvanced"
    >
      <span class="advanced-copy">
        <strong>高级配置</strong>
        <small v-if="advancedConfigCount">已配置 {{ advancedConfigCount }} 项</small>
        <small v-else>断言、变量提取、SQL 和数据驱动均为可选</small>
      </span>
      <svg :class="{ open: showAdvanced }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path d="m6 9 6 6 6-6" />
      </svg>
    </button>
    <div v-if="showAdvanced" id="case-advanced-settings" class="advanced-panel">
      <div class="field">
        <label for="case-assertions">断言 <span class="opt">(JSON 数组，可选)</span></label>
        <textarea id="case-assertions" v-model="form.assertions" rows="3" placeholder='[{"type":"json_eq","path":"code","expected":0}]'></textarea>
      </div>
      <div class="field">
        <label for="case-extract-rules">提取规则 <span class="opt">(JSON 对象，可选)</span></label>
        <textarea id="case-extract-rules" v-model="form.extract_rules" rows="2" placeholder='{"token":"data.token"}'></textarea>
      </div>
      <div class="grid2">
        <div class="field">
          <label for="case-setup-sql">前置 SQL <span class="opt">(JSON 数组，可选)</span></label>
          <textarea id="case-setup-sql" v-model="form.setup_sql" rows="2" placeholder='["DELETE FROM t WHERE id=1"]'></textarea>
        </div>
        <div class="field">
          <label for="case-teardown-sql">后置 SQL <span class="opt">(JSON 数组，可选)</span></label>
          <textarea id="case-teardown-sql" v-model="form.teardown_sql" rows="2" placeholder='["DELETE FROM t WHERE id=1"]'></textarea>
        </div>
      </div>
      <div class="field advanced-last-field">
        <label for="case-datasets">数据集 <span class="opt">(JSON 数组，数据驱动，可选)</span></label>
        <textarea id="case-datasets" v-model="form.datasets" rows="2" placeholder='[{"uid":1},{"uid":2}]'></textarea>
      </div>
    </div>
    <div v-if="formErr" class="form-err" role="alert">{{ formErr }}</div>

    <template #foot>
      <button class="btn btn-ghost" @click="closeModal" :disabled="saving">取消</button>
      <button class="btn btn-primary" @click="save" :disabled="saving || !interfaces.length">{{ saving ? '保存中…' : (editingId == null ? '创建' : '保存') }}</button>
    </template>
  </Modal>

  <!-- 执行结果弹层 -->
  <Modal v-if="showResult" :title="`执行结果 · ${resultCase?.name}`" :max-width="620" @close="showResult = false">
    <div class="verdict">
      <span class="badge" :class="overallPassed ? 'b-pass' : 'b-fail'"><span class="dot"></span>{{ overallPassed ? '通过' : '失败' }}</span>
      <span v-if="runs.length > 1" class="muted">共 {{ runs.length }} 组数据驱动</span>
    </div>

    <div v-for="(r, i) in runs" :key="i" class="run">
      <div class="run-head">
        <span class="badge" :class="r.passed ? 'b-pass' : 'b-fail'"><span class="dot"></span>{{ r.passed ? '通过' : '失败' }}</span>
        <span v-if="runs.length > 1" class="run-idx">数据 #{{ i + 1 }}</span>
        <span v-if="r.attempts" class="muted">尝试 {{ r.attempts }} 次</span>
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
.cards { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; margin-bottom:24px; }
.card { background:var(--surface); border:1px solid var(--border);
  border-radius:14px; padding:18px 20px; box-shadow:var(--shadow-sm); transition:border-color .15s; }
.card:hover { border-color:var(--primary); }
.card .k { font-size:12px; color:var(--text-muted); margin-bottom:10px; font-weight:550; }
.card .v { font-size:27px; font-weight:780; letter-spacing:-.5px; }
.card .v.pri { color:var(--primary); }

.head-actions { display:flex; align-items:center; gap:10px; }
.env-sel { height:32px; padding:0 10px; font-size:12.5px; color:var(--text);
  background:var(--surface-2); border:1px solid var(--border); border-radius:6px; font-family:inherit; }
.env-sel:focus { outline:none; border-color:var(--primary); }

.row { display:grid; grid-template-columns:1.6fr 1.6fr 88px 1.2fr 116px; align-items:center; gap:12px;
  padding:13px 20px; border-bottom:1px solid var(--border); font-size:13px; transition:background .15s; }
.row:last-child { border-bottom:none; }
.row:not(.head):hover { background:var(--surface-2); }
.row.head { font-size:11.5px; font-weight:600; color:var(--text-muted);
  text-transform:uppercase; letter-spacing:.5px; background:var(--surface-2); }
.c-name { display:flex; align-items:center; gap:10px; font-weight:550; }
.c-name .id { color:var(--text-muted); font-family:ui-monospace,Consolas,monospace; font-size:12px;
  background:var(--surface-2); padding:2px 8px; border-radius:6px; flex:none; }
.c-iface { color:var(--text-muted); font-size:12.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.c-exp { font-family:ui-monospace,Consolas,monospace; font-weight:600; }
.c-tags { display:flex; flex-wrap:wrap; gap:5px; }
.c-tags .tag { font-size:11px; padding:2px 8px; border-radius:6px; background:var(--surface-2);
  border:1px solid var(--border); color:var(--text-muted); }
.c-tags .muted { color:var(--text-muted); }
.c-act { text-align:right; display:flex; gap:4px; justify-content:flex-end; }
.icon-btn { display:inline-flex; align-items:center; justify-content:center;
  width:32px; height:32px; padding:0; background:none; border:none; color:var(--text-muted);
  cursor:pointer; border-radius:4px; transition:color .15s,background .15s; }
.icon-btn svg { width:15px; height:15px; }
.icon-btn.run:hover { color:var(--pass-fg); background:var(--pass-bg); }
.icon-btn.edit:hover { color:var(--primary); background:var(--surface-2); }
.icon-btn.del:hover { color:var(--fail-fg); background:var(--fail-bg); }
.icon-btn:disabled { opacity:.5; cursor:not-allowed; }
.spin { width:14px; height:14px; border:2px solid var(--border); border-top-color:var(--primary);
  border-radius:50%; animation:spin .7s linear infinite; }
@keyframes spin { to { transform:rotate(360deg); } }

.state { padding:48px 20px; text-align:center; color:var(--text-muted); font-size:13px; }
.state.err { color:var(--fail-fg); }
.retry { margin-left:12px; }

/* ===== 弹层 ===== */
.grid2 { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
.grid3 { display:grid; grid-template-columns:1.4fr 1fr 1fr; gap:14px; }
.field { margin-bottom:18px; }
.field label { display:block; font-size:12.5px; font-weight:600; margin-bottom:8px; color:var(--text); }
.field label .opt { color:var(--text-muted); font-weight:400; }
.field input, .field select, .field textarea { width:100%; padding:0 12px; font-size:13px; color:var(--text);
  background:var(--surface-2); border:1px solid var(--border); border-radius:8px;
  transition:border-color .15s; font-family:inherit; }
.field input, .field select { height:38px; }
.field textarea { padding:10px 12px; font-family:ui-monospace,Consolas,monospace; font-size:12.5px; resize:vertical; }
.field input:focus, .field select:focus, .field textarea:focus { outline:none; border-color:var(--primary); }

.interface-field select { font-family:ui-monospace,Consolas,monospace; }
.interface-preview { display:flex; align-items:flex-start; gap:12px; margin-top:10px; padding:12px 14px;
  background:var(--surface-2); border:1px solid var(--border); border-radius:10px; }
.method-pill { flex:none; min-width:48px; padding:3px 8px; border-radius:6px; color:var(--primary);
  background:var(--surface); border:1px solid var(--primary); font-size:11px; font-weight:700; text-align:center; }
.preview-copy { min-width:0; display:flex; flex-direction:column; gap:4px; }
.preview-name { font-size:13px; color:var(--text); }
.preview-url { color:var(--text-muted); font-size:12px; overflow-wrap:anywhere; }
.interface-empty { display:flex; align-items:center; justify-content:space-between; gap:20px; padding:14px;
  background:var(--surface-2); border:1px dashed var(--border); border-radius:10px; }
.interface-empty strong { font-size:13px; }
.interface-empty p { margin:5px 0 0; color:var(--text-muted); font-size:12px; line-height:1.6; }
.interface-empty .btn { flex:none; }
.orphan-warning { margin-top:10px; color:var(--fail-fg); font-size:12.5px;
  background:var(--fail-bg); padding:9px 12px; border-radius:8px; }
.state-title { color:var(--text); font-size:14px; font-weight:650; }
.state-copy { margin-top:7px; }
.state-action { margin-top:16px; }

.advanced-toggle { width:100%; display:flex; align-items:center; justify-content:space-between; gap:16px;
  margin:2px 0 18px; padding:12px 14px; color:var(--text); background:var(--surface-2);
  border:1px solid var(--border); border-radius:10px; cursor:pointer; text-align:left;
  font-family:inherit; transition:border-color .15s, background .15s; }
.advanced-toggle:hover { border-color:var(--primary); }
.advanced-toggle:focus-visible { outline:2px solid var(--primary); outline-offset:2px; }
.advanced-toggle svg { width:18px; height:18px; flex:none; color:var(--text-muted); transition:transform .2s; }
.advanced-toggle svg.open { transform:rotate(180deg); }
.advanced-copy { display:flex; flex-direction:column; gap:3px; }
.advanced-copy strong { font-size:13px; }
.advanced-copy small { color:var(--text-muted); font-size:11.5px; font-weight:400; }
.advanced-panel { margin:-8px 0 18px; padding:16px 16px 0; background:var(--surface-2);
  border:1px solid var(--border); border-radius:10px; }
.advanced-last-field { margin-bottom:16px; }

.form-err { color:var(--fail-fg); font-size:12.5px; background:var(--fail-bg); padding:9px 12px; border-radius:8px; }

/* ===== 结果弹层 ===== */
.verdict { display:flex; align-items:center; gap:12px; margin-bottom:16px; }
.verdict .muted { color:var(--text-muted); font-size:12.5px; }
.run { border:1px solid var(--border); border-radius:12px; padding:14px 16px; margin-bottom:12px; }
.run:last-child { margin-bottom:0; }
.run-head { display:flex; align-items:center; gap:12px; margin-bottom:12px; }
.run-head .run-idx { font-weight:600; font-size:12.5px; }
.run-head .muted { color:var(--text-muted); font-size:12px; }
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
@media (max-width:1100px) {
  .cards { grid-template-columns:repeat(3,1fr); }
  .row { grid-template-columns:1.6fr 88px 1fr 116px; }
  .c-iface { display:none; }
}
@media (max-width:640px) {
  .cards { grid-template-columns:1fr; gap:12px; }
  .row { grid-template-columns:1fr 72px 108px; gap:8px; padding:12px 14px; }
  .c-tags { display:none; }
  .grid2, .grid3 { grid-template-columns:1fr; }
  .interface-empty { align-items:flex-start; flex-direction:column; }
  .kv { grid-template-columns:1fr; }
}
</style>
