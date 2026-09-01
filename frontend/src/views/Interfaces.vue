<script setup>
import { useFeedback } from '../composables/feedback'
const { showMessage, confirmAction } = useFeedback()
import { ref, reactive, computed, onMounted } from 'vue'
import { listInterfaces, createInterface, updateInterface, deleteInterface, renameCategory, deleteCategory } from '../api/interface'
import Modal from '../components/Modal.vue'
import KeyValueEditor from '../components/KeyValueEditor.vue'

const items = ref([])
const loading = ref(true)
const error = ref('')

const showModal = ref(false)
const saving = ref(false)
const formErr = ref('')
const editingId = ref(null)   // null=新建,数字=编辑该 id
const requestTab = ref('params')
const form = reactive({
  name: '', method: 'GET', url: '', category: '',
  headers: [], params: [], bodyType: 'none', body: '',
})

// 分类管理面板
const showCatModal = ref(false)
const renamingCat = ref(null)  // 正在重命名的分类原名(null=无)
const newCatName = ref('')
const catErr = ref('')
const catBusy = ref(false)

const METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']
const UNCATEGORIZED = '未分类'

// 折叠状态: {分类名: true=折叠}
const collapsed = reactive({})

const total = computed(() => items.value.length)
const getCount = computed(() => items.value.filter(i => (i.method || '').toUpperCase() === 'GET').length)
const writeCount = computed(() => items.value.filter(i => ['POST','PUT','PATCH','DELETE'].includes((i.method || '').toUpperCase())).length)
const headerCount = computed(() => countEnabledRows(form.headers))
const paramCount = computed(() => countEnabledRows(form.params))
const bodyConfigured = computed(() => form.bodyType === 'json' && Boolean(form.body.trim()))

// 现存分类(datalist 自动补全用),不含"未分类"占位
const existingCategories = computed(() => {
  const set = new Set()
  for (const it of items.value) {
    if (it.category && it.category.trim()) set.add(it.category.trim())
  }
  return [...set].sort()
})

// 按分类分组,"未分类"永远排最后
const groups = computed(() => {
  const map = new Map()
  for (const it of items.value) {
    const key = (it.category && it.category.trim()) || UNCATEGORIZED
    if (!map.has(key)) map.set(key, [])
    map.get(key).push(it)
  }
  const entries = [...map.entries()]
  entries.sort(([a], [b]) => {
    if (a === UNCATEGORIZED) return 1
    if (b === UNCATEGORIZED) return -1
    return a.localeCompare(b, 'zh-CN')
  })
  return entries.map(([name, list]) => ({ name, items: list }))
})

function methodClass(m) {
  return 'm-' + (m || 'get').toLowerCase()
}

function toggleGroup(name) {
  collapsed[name] = !collapsed[name]
}

function newKeyValueRow() {
  return { enabled: true, key: '', value: '' }
}

function countEnabledRows(rows) {
  return rows.filter(row => row.enabled && row.key.trim()).length
}

function rowsFromDict(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return []
  return Object.entries(value).map(([key, itemValue]) => ({
    enabled: true,
    key,
    value: itemValue == null ? '' : String(itemValue),
  }))
}

function validationError(message, tab) {
  const error = new Error(message)
  error.tab = tab
  throw error
}

function rowsToDict(rows, label, tab, caseInsensitive = false) {
  const result = {}
  const seen = new Set()

  rows.forEach((row, index) => {
    if (!row.enabled) return
    const key = row.key.trim()
    const value = row.value ?? ''
    if (!key && !String(value).trim()) return
    if (!key) validationError(label + ' 第 ' + (index + 1) + ' 行缺少名称', tab)

    const uniqueKey = caseInsensitive ? key.toLowerCase() : key
    if (seen.has(uniqueKey)) validationError(label + ' 存在重复 Key：' + key, tab)
    seen.add(uniqueKey)
    result[key] = String(value)
  })

  return Object.keys(result).length ? result : null
}

function defaultRequestTab(method) {
  return ['GET', 'DELETE'].includes((method || '').toUpperCase()) ? 'params' : 'body'
}

function onMethodChange() {
  requestTab.value = defaultRequestTab(form.method)
}

function setBodyType(type) {
  form.bodyType = type
  if (type === 'json' && !form.body.trim()) form.body = '{}'
}

function parseBody() {
  if (form.bodyType === 'none') return null
  const raw = form.body.trim()
  if (!raw) validationError('Body 不能为空，请填写 JSON 对象或选择 none', 'body')
  try {
    const value = JSON.parse(raw)
    if (!value || Array.isArray(value) || typeof value !== 'object') {
      validationError('Body 当前仅支持 JSON 对象', 'body')
    }
    return value
  } catch (error) {
    if (error.tab) throw error
    validationError('Body 不是合法 JSON', 'body')
  }
}

function formatBody() {
  formErr.value = ''
  try {
    const value = parseBody()
    if (value) form.body = JSON.stringify(value, null, 2)
  } catch (error) {
    requestTab.value = 'body'
    formErr.value = error.message
  }
}

// 分类管理:重命名 + 清空
function openCategoryManage() {
  renamingCat.value = null
  newCatName.value = ''
  catErr.value = ''
  showCatModal.value = true
}
function closeCategoryManage() {
  if (catBusy.value) return
  showCatModal.value = false
}
function startRename(oldName) {
  renamingCat.value = oldName
  newCatName.value = oldName
  catErr.value = ''
}
function cancelRename() {
  renamingCat.value = null
  newCatName.value = ''
  catErr.value = ''
}
async function commitRename() {
  const oldName = renamingCat.value
  const nn = newCatName.value.trim()
  if (!nn) { catErr.value = '新名称不能为空'; return }
  if (nn === oldName) { cancelRename(); return }
  catBusy.value = true
  try {
    await renameCategory(oldName, nn)
    await load()
    cancelRename()
  } catch (e) {
    catErr.value = e.message || '重命名失败'
  } finally {
    catBusy.value = false
  }
}
async function onDeleteCategory(name, count) {
  if (!(await confirmAction(`确认清空分类「${name}」? 这会把 ${count} 个接口移到"未分类"(接口本身不删)。`))) return
  catBusy.value = true
  try {
    await deleteCategory(name)
    await load()
  } catch (e) {
    catErr.value = e.message || '清空失败'
  } finally {
    catBusy.value = false
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    items.value = await listInterfaces()
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  form.name = ''
  form.method = 'GET'
  form.url = ''
  form.headers = []
  form.params = [newKeyValueRow()]
  form.bodyType = 'none'
  form.body = ''
  form.category = ''
  requestTab.value = defaultRequestTab(form.method)
  formErr.value = ''
  showModal.value = true
}

// JSON 字段回填成字符串(存进 DB 是 JSON,展示编辑要变成人可读的 JSON 文本)
function jsonToText(v) {
  if (v === null || v === undefined) return ''
  return JSON.stringify(v, null, 2)
}

function openEdit(item) {
  editingId.value = item.id
  form.name = item.name || ''
  form.method = item.method || 'GET'
  form.url = item.url || ''
  form.headers = rowsFromDict(item.headers)
  form.params = rowsFromDict(item.params)
  form.bodyType = item.body == null ? 'none' : 'json'
  form.body = jsonToText(item.body)
  form.category = item.category || ''
  requestTab.value = item.body != null
    ? 'body'
    : (form.params.length ? 'params' : (form.headers.length ? 'headers' : defaultRequestTab(form.method)))
  formErr.value = ''
  showModal.value = true
}

function closeModal() {
  if (saving.value) return
  showModal.value = false
}

async function save() {
  formErr.value = ''
  if (!form.name.trim()) { formErr.value = '请填写接口名称'; return }
  if (!form.url.trim()) { formErr.value = '请填写请求 URL'; return }
  if (!form.url.trim().startsWith('/')) { formErr.value = '请求 URL 必须以 / 开头(环境前缀由所选环境的 base_url 自动补)'; return }

  let headers, params, body
  try {
    headers = rowsToDict(form.headers, 'Headers', 'headers', true)
    params = rowsToDict(form.params, 'Params', 'params')
    body = parseBody()
  } catch (e) {
    requestTab.value = e.tab || requestTab.value
    formErr.value = e.message
    return
  }

  saving.value = true
  try {
    const payload = {
      name: form.name.trim(),
      method: form.method,
      url: form.url.trim(),
      headers, params, body,
      category: form.category.trim() || null,
    }
    if (editingId.value) {
      await updateInterface(editingId.value, payload)
    } else {
      await createInterface(payload)
    }
    showModal.value = false
    await load()
  } catch (e) {
    formErr.value = e.message || '保存失败'
  } finally {
    saving.value = false
  }
}

async function onDelete(id) {
  if (!(await confirmAction('确认删除该接口?'))) return
  try {
    await deleteInterface(id)
    items.value = items.value.filter(i => i.id !== id)
  } catch (e) {
    showMessage(e.message || '删除失败', 'error')
  }
}

onMounted(load)
</script>

<template>
  <div class="cards">
    <div class="card"><div class="k">接口总数</div><div class="v pri">{{ total }}</div></div>
    <div class="card"><div class="k">查询类 GET</div><div class="v pass">{{ getCount }}</div></div>
    <div class="card"><div class="k">写操作类</div><div class="v fail">{{ writeCount }}</div></div>
    <div class="card"><div class="k">覆盖率</div><div class="v">—</div></div>
  </div>

  <div class="panel">
    <div class="panel-head">
      接口列表
      <div class="head-actions">
        <button class="btn btn-ghost" @click="openCategoryManage">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7h4l2-2h10a2 2 0 012 2v10a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" /></svg>
          分类管理
        </button>
        <button class="btn btn-primary" @click="openCreate">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14" /></svg>
          新建接口
        </button>
      </div>
    </div>

    <div v-if="loading" class="state">加载中…</div>
    <div v-else-if="error" class="state err">
      {{ error }}
      <button class="btn btn-ghost retry" @click="load">重试</button>
    </div>
    <div v-else-if="!items.length" class="state">暂无接口,点右上角「新建接口」添加</div>

    <template v-else>
      <div class="row head">
        <span class="c-method">方法</span>
        <span class="c-name">名称</span>
        <span class="c-url">URL</span>
        <span class="c-act">操作</span>
      </div>
      <template v-for="g in groups" :key="g.name">
        <div class="group-head" @click="toggleGroup(g.name)">
          <span class="chevron" :class="{ collapsed: collapsed[g.name] }">▾</span>
          <span class="group-name">{{ g.name }}</span>
          <span class="group-count">{{ g.items.length }}</span>
        </div>
        <template v-if="!collapsed[g.name]">
          <div v-for="(it, i) in g.items" :key="it.id" class="row">
            <span class="c-method"><span class="tag-method" :class="methodClass(it.method)">{{ (it.method || 'GET').toUpperCase() }}</span></span>
            <span class="c-name">
              <span class="id">#{{ i + 1 }}</span>{{ it.name }}
            </span>
            <span class="c-url" :title="it.url">{{ it.url }}</span>
            <span class="c-act">
              <button class="icon-btn" title="编辑" @click="openEdit(it)">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M12 20h9M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z" />
                </svg>
              </button>
              <button class="icon-btn danger" title="删除" @click="onDelete(it.id)">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" />
                </svg>
              </button>
            </span>
          </div>
        </template>
      </template>
    </template>
  </div>

  <!-- 新建/编辑接口弹层 -->
  <Modal v-if="showModal" :title="editingId ? '编辑接口' : '新建接口'" :max-width="760" :busy="saving" @close="closeModal">
    <div class="field">
      <label>接口名称</label>
      <input v-model="form.name" placeholder="如:创建订单" />
    </div>
    <div class="field">
      <label>分类 <span class="opt">(留空归"未分类";可从已有分类里选或新建)</span></label>
      <input v-model="form.category" list="cat-list" placeholder="如:订单管理" />
      <datalist id="cat-list">
        <option v-for="c in existingCategories" :key="c" :value="c" />
      </datalist>
    </div>
    <div class="grid-mu">
      <div class="field">
        <label>请求方法</label>
        <select v-model="form.method" @change="onMethodChange">
          <option v-for="m in METHODS" :key="m" :value="m">{{ m }}</option>
        </select>
      </div>
      <div class="field">
        <label>请求 URL <span class="opt">(只填路径,环境前缀由所选环境的 base_url 自动补)</span></label>
        <input v-model="form.url" placeholder="/orders" />
      </div>
    </div>
    <div class="request-config">
      <div class="request-tabs" role="tablist" aria-label="请求配置">
        <button
          id="request-tab-headers"
          type="button"
          role="tab"
          :aria-selected="requestTab === 'headers'"
          aria-controls="request-panel-headers"
          :class="{ active: requestTab === 'headers' }"
          @click="requestTab = 'headers'"
        >
          Headers <span class="tab-count">{{ headerCount }}</span>
        </button>
        <button
          id="request-tab-params"
          type="button"
          role="tab"
          :aria-selected="requestTab === 'params'"
          aria-controls="request-panel-params"
          :class="{ active: requestTab === 'params' }"
          @click="requestTab = 'params'"
        >
          Params <span class="tab-count">{{ paramCount }}</span>
        </button>
        <button
          id="request-tab-body"
          type="button"
          role="tab"
          :aria-selected="requestTab === 'body'"
          aria-controls="request-panel-body"
          :class="{ active: requestTab === 'body' }"
          @click="requestTab = 'body'"
        >
          Body <span v-if="bodyConfigured" class="tab-ready">已配置</span>
        </button>
      </div>

      <div
        v-show="requestTab === 'headers'"
        id="request-panel-headers"
        class="request-panel"
        role="tabpanel"
        aria-labelledby="request-tab-headers"
      >
        <KeyValueEditor
          v-model="form.headers"
          name-placeholder="Header 名称，如 Authorization"
          value-placeholder="Header 值"
        />
      </div>

      <div
        v-show="requestTab === 'params'"
        id="request-panel-params"
        class="request-panel"
        role="tabpanel"
        aria-labelledby="request-tab-params"
      >
        <KeyValueEditor
          v-model="form.params"
          name-placeholder="参数名，如 page"
          value-placeholder="参数值"
        />
      </div>

      <div
        v-show="requestTab === 'body'"
        id="request-panel-body"
        class="request-panel body-panel"
        role="tabpanel"
        aria-labelledby="request-tab-body"
      >
        <fieldset class="body-type">
          <legend>Body 类型</legend>
          <label :class="{ selected: form.bodyType === 'none' }">
            <input
              type="radio"
              name="body-type"
              value="none"
              :checked="form.bodyType === 'none'"
              @change="setBodyType('none')"
            />
            none
          </label>
          <label :class="{ selected: form.bodyType === 'json' }">
            <input
              type="radio"
              name="body-type"
              value="json"
              :checked="form.bodyType === 'json'"
              @change="setBodyType('json')"
            />
            JSON
          </label>
        </fieldset>

        <div v-if="form.bodyType === 'none'" class="body-empty">
          此请求不发送 Body。
        </div>
        <div v-else class="body-editor">
          <div class="body-editor-head">
            <label for="interface-body-json">JSON 对象</label>
            <button type="button" class="format-json" @click="formatBody">格式化 JSON</button>
          </div>
          <textarea
            id="interface-body-json"
            v-model="form.body"
            rows="8"
            spellcheck="false"
            placeholder='{"name": "test"}'
          ></textarea>
          <div class="config-hint">当前仅支持 JSON 对象，不支持数组、form-data、文件或纯文本。</div>
        </div>

        <div v-if="['GET', 'DELETE'].includes(form.method) && form.bodyType === 'json'" class="compat-warning">
          <strong>兼容性提醒：</strong>{{ form.method }} 请求携带 Body 可能被部分服务端或代理忽略，请确认目标接口支持。
        </div>
      </div>
    </div>
    <div v-if="formErr" class="form-err" role="alert">{{ formErr }}</div>

    <template #foot>
      <button class="btn btn-ghost" @click="closeModal" :disabled="saving">取消</button>
      <button class="btn btn-primary" @click="save" :disabled="saving">{{ saving ? (editingId ? '保存中…' : '创建中…') : (editingId ? '保存' : '创建') }}</button>
    </template>
  </Modal>

  <!-- 分类管理弹层 -->
  <Modal v-if="showCatModal" title="分类管理" :busy="catBusy" @close="closeCategoryManage">
    <div v-if="!groups.filter(g => g.name !== '未分类').length" class="cat-empty">
      还没有分类。建接口时输入分类名即可创建。
    </div>
    <div v-else class="cat-list">
      <div v-for="g in groups.filter(g => g.name !== '未分类')" :key="g.name" class="cat-row">
        <template v-if="renamingCat === g.name">
          <input v-model="newCatName" class="cat-input"
                 @keyup.enter="commitRename" @keyup.esc="cancelRename" />
          <span class="cat-count">{{ g.items.length }} 个接口</span>
          <button class="btn btn-primary btn-sm" @click="commitRename" :disabled="catBusy">保存</button>
          <button class="btn btn-ghost btn-sm" @click="cancelRename" :disabled="catBusy">取消</button>
        </template>
        <template v-else>
          <span class="cat-name">{{ g.name }}</span>
          <span class="cat-count">{{ g.items.length }} 个接口</span>
          <button class="icon-btn" title="重命名" @click="startRename(g.name)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 20h9M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z" />
            </svg>
          </button>
          <button class="icon-btn danger" title="清空(接口移到未分类)" @click="onDeleteCategory(g.name, g.items.length)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" />
            </svg>
          </button>
        </template>
      </div>
    </div>
    <div v-if="catErr" class="form-err">{{ catErr }}</div>
    <template #foot>
      <button class="btn btn-ghost" @click="closeCategoryManage" :disabled="catBusy">关闭</button>
    </template>
  </Modal>
</template>

<style scoped>
.cards { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:24px; }
.card { background:var(--surface); border:1px solid var(--border);
  border-radius:14px; padding:18px 20px; box-shadow:var(--shadow-sm);
  transition:border-color .15s; }
.card:hover { border-color:var(--primary); }
.card .k { font-size:12px; color:var(--text-muted); margin-bottom:10px; font-weight:550; }
.card .v { font-size:27px; font-weight:780; letter-spacing:-.5px; }
.card .v.pass { color:var(--pass-fg); }
.card .v.fail { color:var(--fail-fg); }
.card .v.pri { color:var(--primary); }

.row { display:grid; grid-template-columns:80px 1.4fr 2fr 100px; align-items:center; gap:12px;
  padding:13px 20px; border-bottom:1px solid var(--border); font-size:13px; transition:background .15s; }
.row:last-child { border-bottom:none; }
.row:not(.head):hover { background:var(--surface-2); }
.row.head { font-size:11.5px; font-weight:600; color:var(--text-muted);
  text-transform:uppercase; letter-spacing:.5px; background:var(--surface-2); }
.c-name { display:flex; align-items:center; gap:10px; font-weight:550; }
.c-name .id { color:var(--text-muted); font-family:ui-monospace,Consolas,monospace; font-size:12px;
  background:var(--surface-2); padding:2px 8px; border-radius:6px; }
.c-url { color:var(--text-muted); font-family:ui-monospace,Consolas,monospace; font-size:12px;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.c-act { text-align:right; display:flex; justify-content:flex-end; gap:2px; }
.icon-btn { display:inline-flex; align-items:center; justify-content:center;
  width:32px; height:32px; padding:0; background:none; border:none; color:var(--text-muted);
  cursor:pointer; border-radius:4px; transition:color .15s,background .15s; }
.icon-btn svg { width:16px; height:16px; }
.icon-btn:hover { color:var(--primary); background:var(--surface-2); }
.icon-btn.danger:hover { color:var(--fail-fg); background:var(--fail-bg); }

.state { padding:48px 20px; text-align:center; color:var(--text-muted); font-size:13px; }
.state.err { color:var(--fail-fg); }
.retry { margin-left:12px; }

/* ===== 分组头 ===== */
.group-head { display:flex; align-items:center; gap:10px;
  padding:11px 20px; background:var(--surface-2); border-bottom:1px solid var(--border);
  font-size:12.5px; font-weight:600; cursor:pointer; user-select:none;
  transition:background .15s; }
.group-head:hover { background:var(--border); }
.group-head .chevron { display:inline-block; width:12px; color:var(--text-muted);
  transition:transform .15s; font-size:10px; }
.group-head .chevron.collapsed { transform:rotate(-90deg); }
.group-head .group-name { color:var(--text); flex:1; }
.group-head .group-count { color:var(--text-muted); font-weight:500;
  background:var(--surface); padding:1px 9px; border-radius:10px; font-size:11.5px; }

/* ===== 弹层 ===== */
.grid-mu { display:grid; grid-template-columns:120px 1fr; gap:14px; }
.field { margin-bottom:18px; }
.field label { display:block; font-size:12.5px; font-weight:600; margin-bottom:8px; color:var(--text); }
.field label .opt { color:var(--text-muted); font-weight:400; }
.field input, .field select, .field textarea { width:100%; padding:0 12px; font-size:13px; color:var(--text);
  background:var(--surface-2); border:1px solid var(--border); border-radius:8px;
  transition:border-color .15s; font-family:inherit; }
.field input, .field select { height:38px; }
.field textarea { padding:10px 12px; font-family:ui-monospace,Consolas,monospace; font-size:12.5px; resize:vertical; }
.field input:focus, .field select:focus, .field textarea:focus { outline:none; border-color:var(--primary); }

.request-config { margin-top:2px; margin-bottom:18px; }
.request-tabs { display:flex; gap:2px; padding:6px 8px 0; background:var(--surface-2); border-bottom:1px solid var(--border); }
.request-tabs button { display:flex; align-items:center; gap:7px; min-height:38px; padding:0 12px;
  color:var(--text-muted); background:transparent; border:1px solid transparent; border-bottom:none;
  border-radius:8px 8px 0 0; cursor:pointer; font:600 12.5px inherit; transition:color .15s,background .15s,border-color .15s; }
.request-tabs button:hover { color:var(--text); background:var(--surface); }
.request-tabs button.active { color:var(--primary); background:var(--surface); border-color:var(--border); position:relative; }
.request-tabs button.active::after { content:''; position:absolute; left:0; right:0; bottom:-1px; height:1px; background:var(--surface); }
.request-tabs button:focus-visible { outline:2px solid var(--primary); outline-offset:-2px; }
.tab-count { display:inline-flex; align-items:center; justify-content:center; min-width:19px; height:19px; padding:0 5px;
  color:var(--text-muted); background:var(--border); border-radius:10px; font-size:10.5px; }
.request-tabs button.active .tab-count { color:var(--primary); background:var(--primary-bg); }
.tab-ready { padding:2px 6px; color:var(--pass-fg); background:var(--pass-bg); border-radius:9px; font-size:10.5px; }
.request-panel { padding:12px 0 0; background:var(--surface); }
.config-hint { margin-bottom:10px; color:var(--text-muted); font-size:11.5px; line-height:1.55; }
.body-type { display:flex; align-items:center; gap:6px; margin:0 0 14px; padding:0; border:0; }
.body-type legend { float:left; margin-right:8px; color:var(--text); font-size:12px; font-weight:600; line-height:32px; }
.body-type label { display:flex; align-items:center; gap:6px; height:32px; padding:0 12px; color:var(--text-muted);
  background:var(--surface-2); border:1px solid var(--border); border-radius:7px; cursor:pointer; font-size:12px; }
.body-type label.selected { color:var(--primary); border-color:var(--primary); background:var(--primary-bg); }
.body-type input { accent-color:var(--primary); cursor:pointer; }
.body-empty { padding:26px 16px; color:var(--text-muted); background:var(--surface-2); border:1px dashed var(--border);
  border-radius:8px; text-align:center; font-size:12.5px; }
.body-editor-head { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:8px; }
.body-editor-head label { color:var(--text); font-size:12px; font-weight:600; }
.format-json { padding:5px 9px; color:var(--primary); background:transparent; border:1px solid var(--border);
  border-radius:6px; cursor:pointer; font:600 11.5px inherit; transition:background .15s,border-color .15s; }
.format-json:hover { background:var(--primary-bg); border-color:var(--primary); }
.format-json:focus-visible { outline:2px solid var(--primary); outline-offset:2px; }
.body-editor textarea { width:100%; padding:11px 12px; color:var(--text); background:var(--surface-2);
  border:1px solid var(--border); border-radius:8px; resize:vertical; font:12.5px/1.55 ui-monospace,Consolas,monospace; }
.body-editor textarea:focus { outline:none; border-color:var(--primary); }
.body-editor .config-hint { margin:7px 0 0; }
.compat-warning { margin-top:12px; padding:10px 12px; color:var(--text); background:var(--warning-bg, #fff7e6);
  border:1px solid var(--warning-border, #f3d18b); border-radius:8px; font-size:11.5px; line-height:1.55; }
.form-err { color:var(--fail-fg); font-size:12.5px; background:var(--fail-bg); padding:9px 12px; border-radius:8px; }

/* ===== 分类管理弹层 ===== */
.head-actions { display:flex; gap:8px; }
.cat-empty { padding:32px 0; text-align:center; color:var(--text-muted); font-size:13px; }
.cat-list { display:flex; flex-direction:column; gap:6px; }
.cat-row { display:flex; align-items:center; gap:12px;
  padding:10px 14px; background:var(--surface-2); border-radius:8px; }
.cat-name { flex:1; font-weight:550; font-size:13px; }
.cat-count { color:var(--text-muted); font-size:12px;
  background:var(--surface); padding:2px 8px; border-radius:10px; }
.cat-input { flex:1; height:32px; padding:0 10px; font-size:13px;
  background:var(--surface); border:1px solid var(--primary); border-radius:6px; }
.btn-sm { height:32px; padding:0 12px; font-size:12.5px; }

/* ===== 响应式 ===== */
@media (max-width:1100px) {
  .cards { grid-template-columns:repeat(2,1fr); }
}
@media (max-width:560px) {
  .cards { grid-template-columns:1fr; gap:12px; }
  .row { grid-template-columns:64px 1fr 56px; gap:8px; padding:12px 14px; }
  .c-url { display:none; }
  .grid-mu { grid-template-columns:1fr; }
  .request-tabs { overflow-x:auto; }
  .request-tabs button { flex:0 0 auto; }
  .request-panel { padding:12px 0 0; }
  .body-type { align-items:flex-start; flex-wrap:wrap; }
  .body-type legend { width:100%; line-height:1.4; margin-bottom:2px; }
}
</style>
