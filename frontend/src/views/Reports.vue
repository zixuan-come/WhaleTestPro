<script setup>
import { ref, computed, onMounted } from 'vue'
import { listReports } from '../api/report'
import { formatShanghaiDateTime } from '../utils/time'

const items = ref([])
const page = ref(1)
const pageSize = ref(20)
const totalPages = ref(0)
const reportTotal = ref(0)
const passedTotal = ref(0)
const failedTotal = ref(0)
const passRateTotal = ref(0)
const loading = ref(true)
const error = ref('')
const openId = ref(null)   // 当前展开查看 detail 的报告 id

const pageStart = computed(() => reportTotal.value ? (page.value - 1) * pageSize.value + 1 : 0)
const pageEnd = computed(() => Math.min(page.value * pageSize.value, reportTotal.value))
const passRate = computed(() => Math.round(passRateTotal.value * 100))


function fmtDetail(v) {
  if (v == null) return '无明细'
  try { return JSON.stringify(v, null, 2) } catch { return String(v) }
}

function toggle(id) {
  openId.value = openId.value === id ? null : id
}

async function load(targetPage = page.value) {
  loading.value = true
  error.value = ''
  try {
    const data = await listReports(targetPage, pageSize.value)
    items.value = data.items
    page.value = data.page
    totalPages.value = data.total_pages
    reportTotal.value = data.total
    passedTotal.value = data.passed_count
    failedTotal.value = data.failed_count
    passRateTotal.value = data.pass_rate
    openId.value = null
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function changePage(targetPage) {
  if (targetPage < 1 || targetPage > totalPages.value || targetPage === page.value) return
  load(targetPage)
}

function changePageSize() {
  page.value = 1
  load(1)
}

onMounted(load)
</script>

<template>
  <div class="cards">
    <div class="card"><div class="k">报告总数</div><div class="v pri">{{ reportTotal }}</div></div>
    <div class="card"><div class="k">通过</div><div class="v pass">{{ passedTotal }}</div></div>
    <div class="card"><div class="k">失败</div><div class="v fail">{{ failedTotal }}</div></div>
    <div class="card"><div class="k">通过率</div><div class="v">{{ passRate }}<span class="unit">%</span></div></div>
  </div>

  <div class="panel">
    <div class="panel-head">
      测试报告
      <span class="count">共 {{ reportTotal }} 条</span>
    </div>

    <div v-if="loading" class="state">加载中…</div>
    <div v-else-if="error" class="state err">
      {{ error }}
      <button class="btn btn-ghost retry" @click="load">重试</button>
    </div>
    <div v-else-if="!items.length" class="state">
      {{ reportTotal ? '当前页暂无报告' : '暂无报告,跑一次用例后这里会出现执行结果' }}
    </div>

    <template v-else>
      <div class="row head">
        <span class="c-status">状态</span>
        <span class="c-name">报告</span>
        <span class="c-time">执行时间</span>
        <span class="c-act">明细</span>
      </div>
      <template v-for="(r, i) in items" :key="r.id">
        <div class="row" :class="{ open: openId === r.id }" @click="toggle(r.id)">
          <span class="c-status">
            <span class="badge" :class="r.passed ? 'b-pass' : 'b-fail'">
              <span class="dot"></span>{{ r.passed ? '通过' : '失败' }}
            </span>
          </span>
          <span class="c-name">
            <span class="id">#{{ pageStart + i }}</span>{{ r.case_name || '用例已删除' }}
          </span>
          <span class="c-time">{{ formatShanghaiDateTime(r.created_at) }}</span>
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

    <div v-if="reportTotal" class="pagination">
      <span class="page-summary">显示 {{ pageStart }}-{{ pageEnd }} 条</span>
      <label class="page-size">每页
        <select v-model.number="pageSize" @change="changePageSize">
          <option :value="10">10</option>
          <option :value="20">20</option>
          <option :value="50">50</option>
          <option :value="100">100</option>
        </select>
      </label>
      <button class="btn btn-ghost btn-sm" :disabled="loading || page <= 1" @click="changePage(page - 1)">上一页</button>
      <span class="page-number">{{ page }} / {{ totalPages }}</span>
      <button class="btn btn-ghost btn-sm" :disabled="loading || page >= totalPages" @click="changePage(page + 1)">下一页</button>
    </div>
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
.pagination { display:flex; align-items:center; justify-content:flex-end; gap:12px; padding:14px 20px; border-top:1px solid var(--border); color:var(--text-muted); font-size:12px; }
.page-size { display:flex; align-items:center; gap:6px; }
.page-size select { height:30px; padding:0 8px; color:var(--text); background:var(--surface-2); border:1px solid var(--border); border-radius:6px; font:inherit; }
.page-number { min-width:52px; text-align:center; color:var(--text); font-weight:600; }

/* ===== 响应式 ===== */
@media (max-width:1100px) {
  .cards { grid-template-columns:repeat(2,1fr); }
}
@media (max-width:560px) {
  .cards { grid-template-columns:1fr; gap:12px; }
  .row { grid-template-columns:80px 1fr 44px; gap:8px; padding:12px 14px; }
  .c-time { display:none; }
  .pagination { flex-wrap:wrap; justify-content:center; padding:12px 14px; }
  .page-summary { width:100%; text-align:center; }
}
</style>
