<script setup>
import { ref, computed, onMounted } from 'vue'
import { listReports } from '../api/report'

const items = ref([])
const loading = ref(true)
const error = ref('')
const openId = ref(null)   // 当前展开查看 detail 的报告 id

const total = computed(() => items.value.length)
const passCount = computed(() => items.value.filter(r => r.passed).length)
const failCount = computed(() => items.value.filter(r => !r.passed).length)
const passRate = computed(() => total.value ? Math.round(passCount.value / total.value * 100) : 0)

function fmtTime(s) {
  if (!s) return '—'
  const d = new Date(s)
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

function fmtDetail(v) {
  if (v == null) return '无明细'
  try { return JSON.stringify(v, null, 2) } catch { return String(v) }
}

function toggle(id) {
  openId.value = openId.value === id ? null : id
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    items.value = await listReports()
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="cards">
    <div class="card"><div class="k">报告总数</div><div class="v pri">{{ total }}</div></div>
    <div class="card"><div class="k">通过</div><div class="v pass">{{ passCount }}</div></div>
    <div class="card"><div class="k">失败</div><div class="v fail">{{ failCount }}</div></div>
    <div class="card"><div class="k">通过率</div><div class="v">{{ passRate }}<span class="unit">%</span></div></div>
  </div>

  <div class="panel">
    <div class="panel-head">
      测试报告
      <span class="count">共 {{ total }} 条</span>
    </div>

    <div v-if="loading" class="state">加载中…</div>
    <div v-else-if="error" class="state err">
      {{ error }}
      <button class="btn btn-ghost retry" @click="load">重试</button>
    </div>
    <div v-else-if="!items.length" class="state">暂无报告,跑一次用例后这里会出现执行结果</div>

    <template v-else>
      <div class="row head">
        <span class="c-status">状态</span>
        <span class="c-name">报告</span>
        <span class="c-time">执行时间</span>
        <span class="c-act">明细</span>
      </div>
      <template v-for="r in items" :key="r.id">
        <div class="row" :class="{ open: openId === r.id }" @click="toggle(r.id)">
          <span class="c-status">
            <span class="badge" :class="r.passed ? 'b-pass' : 'b-fail'">
              <span class="dot"></span>{{ r.passed ? '通过' : '失败' }}
            </span>
          </span>
          <span class="c-name">
            <span class="id">#{{ r.id }}</span>用例 {{ r.case_id }}
          </span>
          <span class="c-time">{{ fmtTime(r.created_at) }}</span>
          <span class="c-act">
            <svg class="chev" :class="{ up: openId === r.id }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M6 9l6 6 6-6" />
            </svg>
          </span>
        </div>
        <div v-if="openId === r.id" class="detail">
          <pre>{{ fmtDetail(r.detail) }}</pre>
        </div>
      </template>
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
.card .v .unit { font-size:16px; font-weight:600; margin-left:2px; color:var(--text-muted); }
.card .v.pass { color:var(--pass-fg); }
.card .v.fail { color:var(--fail-fg); }
.card .v.pri { color:var(--primary); }

.row { display:grid; grid-template-columns:96px 1.6fr 1.4fr 60px; align-items:center; gap:12px;
  padding:13px 20px; border-bottom:1px solid var(--border); font-size:13px; cursor:pointer;
  transition:background .15s; }
.row:not(.head):hover { background:var(--surface-2); }
.row.open { background:var(--surface-2); }
.row.head { font-size:11.5px; font-weight:600; color:var(--text-muted);
  text-transform:uppercase; letter-spacing:.5px; background:var(--surface-2); cursor:default; }
.c-name { display:flex; align-items:center; gap:10px; font-weight:550; }
.c-name .id { color:var(--text-muted); font-family:ui-monospace,Consolas,monospace; font-size:12px;
  background:var(--surface-2); padding:2px 8px; border-radius:6px; }
.c-time { color:var(--text-muted); font-family:ui-monospace,Consolas,monospace; font-size:12px; }
.c-act { text-align:right; }
.chev { width:16px; height:16px; color:var(--text-muted); transition:transform .2s; }
.chev.up { transform:rotate(180deg); }

.detail { border-bottom:1px solid var(--border); background:var(--bg); padding:0 20px; }
.detail pre { margin:0; padding:16px 0; font-family:ui-monospace,Consolas,monospace; font-size:12px;
  line-height:1.6; color:var(--text); white-space:pre-wrap; word-break:break-all; max-height:360px; overflow:auto; }

.state { padding:48px 20px; text-align:center; color:var(--text-muted); font-size:13px; }
.state.err { color:var(--fail-fg); }
.retry { margin-left:12px; }

/* ===== 响应式 ===== */
@media (max-width:1100px) {
  .cards { grid-template-columns:repeat(2,1fr); }
}
@media (max-width:560px) {
  .cards { grid-template-columns:1fr; gap:12px; }
  .row { grid-template-columns:80px 1fr 44px; gap:8px; padding:12px 14px; }
  .c-time { display:none; }
}
</style>
