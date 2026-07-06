<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { listInterfaces, createInterface, updateInterface, deleteInterface, renameCategory, deleteCategory } from '../api/interface'
import Modal from '../components/Modal.vue'

const items = ref([])
const loading = ref(true)
const error = ref('')

const showModal = ref(false)
const saving = ref(false)
const formErr = ref('')
const editingId = ref(null)   // null=新建,数字=编辑该 id
const form = reactive({ name: '', method: 'GET', url: '', headers: '', params: '', body: '', category: '' })

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
const writeCount = computed(() => items.value.filter(i => ['POST','PUT','DELETE'].includes((i.method || '').toUpperCase())).length)

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
  if (!confirm(`确认清空分类「${name}」? 这会把 ${count} 个接口移到"未分类"(接口本身不删)。`)) return
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
  form.headers = ''
  form.params = ''
  form.body = ''
  form.category = ''
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
  form.headers = jsonToText(item.headers)
  form.params = jsonToText(item.params)
  form.body = jsonToText(item.body)
  form.category = item.category || ''
  formErr.value = ''
  showModal.value = true
}

function closeModal() {
  if (saving.value) return
  showModal.value = false
}

// 空串 → null;非空 → 解析 JSON,失败抛错(带字段名)
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
  if (!form.name.trim()) { formErr.value = '请填写接口名称'; return }
  if (!form.url.trim()) { formErr.value = '请填写请求 URL'; return }
  if (!form.url.trim().startsWith('/')) { formErr.value = '请求 URL 必须以 / 开头(环境前缀由所选环境的 base_url 自动补)'; return }

  let headers, params, body
  try {
    headers = parseJsonField(form.headers, 'Headers')
    params = parseJsonField(form.params, 'Params')
    body = parseJsonField(form.body, 'Body')
  } catch (e) {
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
  if (!confirm('确认删除该接口?')) return
  try {
    await deleteInterface(id)
    items.value = items.value.filter(i => i.id !== id)
  } catch (e) {
    alert(e.message || '删除失败')
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
  <Modal v-if="showModal" :title="editingId ? '编辑接口' : '新建接口'" :busy="saving" @close="closeModal">
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
        <select v-model="form.method">
          <option v-for="m in METHODS" :key="m" :value="m">{{ m }}</option>
        </select>
      </div>
      <div class="field">
        <label>请求 URL <span class="opt">(只填路径,环境前缀由所选环境的 base_url 自动补)</span></label>
        <input v-model="form.url" placeholder="/orders" />
      </div>
    </div>
    <div class="field">
      <label>Headers <span class="opt">(JSON,可选)</span></label>
      <textarea v-model="form.headers" rows="2" placeholder='{"Authorization": "Bearer xxx"}'></textarea>
    </div>
    <div class="field">
      <label>Params <span class="opt">(JSON,可选)</span></label>
      <textarea v-model="form.params" rows="2" placeholder='{"page": 1}'></textarea>
    </div>
    <div class="field">
      <label>Body <span class="opt">(JSON,可选)</span></label>
      <textarea v-model="form.body" rows="3" placeholder='{"name": "test"}'></textarea>
    </div>
    <div v-if="formErr" class="form-err">{{ formErr }}</div>

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
}
</style>
