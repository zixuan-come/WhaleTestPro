<script setup>
import { ref, computed, onMounted } from 'vue'
import { listInterfaces, deleteInterface } from '../api/interface'

const items = ref([])
const loading = ref(true)
const error = ref('')

const total = computed(() => items.value.length)
const getCount = computed(() => items.value.filter(i => (i.method || '').toUpperCase() === 'GET').length)
const writeCount = computed(() => items.value.filter(i => ['POST','PUT','DELETE'].includes((i.method || '').toUpperCase())).length)

function methodClass(m) {
  return 'm-' + (m || 'get').toLowerCase()
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
      <span class="count">共 {{ total }} 条</span>
    </div>

    <div v-if="loading" class="state">加载中…</div>
    <div v-else-if="error" class="state err">
      {{ error }}
      <button class="btn btn-ghost retry" @click="load">重试</button>
    </div>
    <div v-else-if="!items.length" class="state">暂无接口,点右上角「新建用例」添加</div>

    <template v-else>
      <div class="row head">
        <span class="c-method">方法</span>
        <span class="c-name">名称</span>
        <span class="c-url">URL</span>
        <span class="c-act">操作</span>
      </div>
      <div v-for="it in items" :key="it.id" class="row">
        <span class="c-method"><span class="tag-method" :class="methodClass(it.method)">{{ (it.method || 'GET').toUpperCase() }}</span></span>
        <span class="c-name">
          <span class="id">#{{ it.id }}</span>{{ it.name }}
        </span>
        <span class="c-url" :title="it.url">{{ it.url }}</span>
        <span class="c-act">
          <button class="icon-btn" title="删除" @click="onDelete(it.id)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" />
            </svg>
          </button>
        </span>
      </div>
    </template>
  </div>
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

.row { display:grid; grid-template-columns:80px 1.4fr 2fr 70px; align-items:center; gap:12px;
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
.c-act { text-align:right; }
.icon-btn { display:inline-flex; align-items:center; justify-content:center;
  width:32px; height:32px; padding:0; background:none; border:none; color:var(--text-muted);
  cursor:pointer; border-radius:4px; transition:color .15s,background .15s; }
.icon-btn svg { width:16px; height:16px; }
.icon-btn:hover { color:var(--fail-fg); background:var(--fail-bg); }

.state { padding:48px 20px; text-align:center; color:var(--text-muted); font-size:13px; }
.state.err { color:var(--fail-fg); }
.retry { margin-left:12px; }

/* ===== 响应式 ===== */
/* 笔记本/平板:统计卡 4 列 → 2 列 */
@media (max-width:1100px) {
  .cards { grid-template-columns:repeat(2,1fr); }
}
/* 手机:统计卡 1 列;表格去掉 URL 列,栅格收成 3 栏 */
@media (max-width:560px) {
  .cards { grid-template-columns:1fr; gap:12px; }
  .row { grid-template-columns:64px 1fr 56px; gap:8px; padding:12px 14px; }
  .c-url { display:none; }
}
</style>
