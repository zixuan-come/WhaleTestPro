<script setup>
import { ref, reactive, onMounted } from 'vue'
import {
  listEnvironments, createEnvironment, updateEnvironment, deleteEnvironment,
} from '../api/environment'
import Modal from '../components/Modal.vue'

const items = ref([])
const loading = ref(true)
const error = ref('')

// 弹层表单状态
const showModal = ref(false)
const editingId = ref(null)          // null = 新建, 数字 = 编辑
const saving = ref(false)
const formErr = ref('')
const form = reactive({ name: '', base_url: '' })
const pairs = ref([])                // [{ key, value }] 键值对编辑
const refSyntax = '{{key}}'          // 提示文案里的字面量,放常量避免污染模板 mustache 解析

function varCount(env) {
  return env.variables ? Object.keys(env.variables).length : 0
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    items.value = await listEnvironments()
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  form.name = ''
  form.base_url = ''
  pairs.value = [{ key: '', value: '' }]
  formErr.value = ''
  showModal.value = true
}

function openEdit(env) {
  editingId.value = env.id
  form.name = env.name
  form.base_url = env.base_url
  pairs.value = Object.entries(env.variables || {})
    .map(([k, v]) => ({ key: k, value: typeof v === 'string' ? v : JSON.stringify(v) }))
  if (!pairs.value.length) pairs.value = [{ key: '', value: '' }]
  formErr.value = ''
  showModal.value = true
}

function closeModal() {
  if (saving.value) return
  showModal.value = false
}

function addPair() {
  pairs.value.push({ key: '', value: '' })
}

function removePair(i) {
  pairs.value.splice(i, 1)
  if (!pairs.value.length) pairs.value = [{ key: '', value: '' }]
}

async function save() {
  formErr.value = ''
  if (!form.name.trim()) { formErr.value = '请填写环境名称'; return }
  if (!form.base_url.trim()) { formErr.value = '请填写 Base URL'; return }

  // 键值对数组 → variables 字典(空 key 的行丢弃)
  const variables = {}
  for (const p of pairs.value) {
    const k = p.key.trim()
    if (k) variables[k] = p.value
  }
  const payload = {
    name: form.name.trim(),
    base_url: form.base_url.trim(),
    variables: Object.keys(variables).length ? variables : null,
  }

  saving.value = true
  try {
    if (editingId.value == null) {
      await createEnvironment(payload)
    } else {
      await updateEnvironment(editingId.value, payload)
    }
    showModal.value = false
    await load()
  } catch (e) {
    formErr.value = e.message || '保存失败'
  } finally {
    saving.value = false
  }
}

async function onDelete(env) {
  if (!confirm(`确认删除环境「${env.name}」?`)) return
  try {
    await deleteEnvironment(env.id)
    items.value = items.value.filter(i => i.id !== env.id)
  } catch (e) {
    alert(e.message || '删除失败')
  }
}

onMounted(load)
</script>

<template>
  <div class="panel">
    <div class="panel-head">
      环境列表
      <button class="btn btn-primary" @click="openCreate">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14" /></svg>
        新建环境
      </button>
    </div>

    <div v-if="loading" class="state">加载中…</div>
    <div v-else-if="error" class="state err">
      {{ error }}
      <button class="btn btn-ghost retry" @click="load">重试</button>
    </div>
    <div v-else-if="!items.length" class="state">暂无环境,点右上角「新建环境」添加</div>

    <template v-else>
      <div class="row head">
        <span class="c-name">名称</span>
        <span class="c-url">Base URL</span>
        <span class="c-vars">变量</span>
        <span class="c-act">操作</span>
      </div>
      <div v-for="(env, i) in items" :key="env.id" class="row">
        <span class="c-name"><span class="id">#{{ i + 1 }}</span>{{ env.name }}</span>
        <span class="c-url" :title="env.base_url">{{ env.base_url }}</span>
        <span class="c-vars"><span class="pill">{{ varCount(env) }} 个</span></span>
        <span class="c-act">
          <button class="icon-btn" title="编辑" @click="openEdit(env)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" /></svg>
          </button>
          <button class="icon-btn del" title="删除" @click="onDelete(env)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" /></svg>
          </button>
        </span>
      </div>
    </template>
  </div>

  <!-- 新建/编辑弹层 -->
  <Modal v-if="showModal" :title="editingId == null ? '新建环境' : '编辑环境'" :max-width="520" :busy="saving" @close="closeModal">
    <div class="field">
      <label>环境名称</label>
      <input v-model="form.name" placeholder="如:测试环境 / 预发 / 生产" />
    </div>
    <div class="field">
      <label>Base URL</label>
      <input v-model="form.base_url" placeholder="https://api.example.com" />
    </div>
    <div class="field">
      <label>环境变量<span class="hint">接口用例里用 {{ refSyntax }} 引用</span></label>
      <div class="pairs">
        <div v-for="(p, i) in pairs" :key="i" class="pair">
          <input v-model="p.key" class="p-key" placeholder="key" />
          <input v-model="p.value" class="p-val" placeholder="value" />
          <button class="icon-btn del" title="移除" @click="removePair(i)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14" /></svg>
          </button>
        </div>
        <button class="btn btn-ghost add" @click="addPair">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14" /></svg>
          添加变量
        </button>
      </div>
    </div>
    <div v-if="formErr" class="form-err">{{ formErr }}</div>

    <template #foot>
      <button class="btn btn-ghost" @click="closeModal" :disabled="saving">取消</button>
      <button class="btn btn-primary" @click="save" :disabled="saving">{{ saving ? '保存中…' : '保存' }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.row { display:grid; grid-template-columns:1.4fr 2fr 90px 84px; align-items:center; gap:12px;
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
.pill { font-size:11px; font-weight:600; color:var(--primary); background:var(--ring);
  padding:3px 10px; border-radius:99px; }
.c-act { text-align:right; display:flex; gap:4px; justify-content:flex-end; }
.icon-btn { display:inline-flex; align-items:center; justify-content:center;
  width:32px; height:32px; padding:0; background:none; border:none; color:var(--text-muted);
  cursor:pointer; border-radius:4px; transition:color .15s,background .15s; }
.icon-btn svg { width:16px; height:16px; }
.icon-btn:hover { color:var(--primary); background:var(--surface-2); }
.icon-btn.del:hover { color:var(--fail-fg); background:var(--fail-bg); }

.state { padding:48px 20px; text-align:center; color:var(--text-muted); font-size:13px; }
.state.err { color:var(--fail-fg); }
.retry { margin-left:12px; }

/* ===== 弹层 ===== */
.field { margin-bottom:18px; }
.field label { display:block; font-size:12.5px; font-weight:600; margin-bottom:8px; color:var(--text); }
.field label .hint { font-weight:400; color:var(--text-muted); margin-left:8px; font-size:11.5px; }
.field input { width:100%; height:38px; padding:0 12px; font-size:13px; color:var(--text);
  background:var(--surface-2); border:1px solid var(--border); border-radius:8px;
  transition:border-color .15s; font-family:inherit; }
.field input:focus { outline:none; border-color:var(--primary); }

.pairs { display:flex; flex-direction:column; gap:8px; }
.pair { display:grid; grid-template-columns:1fr 1.4fr 32px; gap:8px; align-items:center; }
.pair input { height:36px; }
.add { align-self:flex-start; height:34px; margin-top:2px; }

.form-err { color:var(--fail-fg); font-size:12.5px; background:var(--fail-bg);
  padding:9px 12px; border-radius:8px; }

/* ===== 响应式 ===== */
@media (max-width:640px) {
  .row { grid-template-columns:1fr 72px 76px; gap:8px; padding:12px 14px; }
  .c-url { display:none; }
  .pair { grid-template-columns:1fr 1.2fr 32px; }
}
</style>
