<script setup>
import { ref, computed, onMounted } from 'vue'
import { runRegression } from '../api/regression'
import { listEnvironments } from '../api/environment'

const envs = ref([])
const selectedEnv = ref('')
const tag = ref('')
const notify = ref(false)

const running = ref(false)
const error = ref('')
const summary = ref(null)

const passRate = computed(() => summary.value ? Math.round((summary.value.pass_rate || 0) * 100) : 0)
const coverage = computed(() => summary.value ? Math.round((summary.value.interface_coverage || 0) * 100) : 0)

async function loadEnvs() {
  try {
    envs.value = await listEnvironments()
  } catch { /* 环境拉不到不阻塞回归 */ }
}

async function onRun() {
  running.value = true
  error.value = ''
  try {
    summary.value = await runRegression({
      envId: selectedEnv.value || undefined,
      tag: tag.value.trim() || undefined,
      notify: notify.value,
    })
  } catch (e) {
    error.value = e.message || '回归执行失败'
  } finally {
    running.value = false
  }
}

onMounted(loadEnvs)
</script>

<template>
  <div class="panel run-panel">
    <div class="panel-head">回归执行</div>
    <div class="run-body">
      <p class="hint">不填标签则跑全部用例;填标签只跑带该标签的用例。回归会统计通过率与接口覆盖率,并可选飞书通知。</p>
      <div class="controls">
        <div class="field">
          <label>环境</label>
          <select v-model="selectedEnv">
            <option value="">不指定环境</option>
            <option v-for="e in envs" :key="e.id" :value="e.id">{{ e.name }}</option>
          </select>
        </div>
        <div class="field">
          <label>标签筛选 <span class="opt">(可选)</span></label>
          <input v-model="tag" placeholder="如:smoke" />
        </div>
        <label class="chk">
          <input type="checkbox" v-model="notify" />
          <span>飞书通知</span>
        </label>
        <button class="btn btn-primary run-btn" :disabled="running" @click="onRun">
          <svg v-if="!running" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 4l14 8-14 8V4Z" /></svg>
          <span v-else class="spin"></span>
          {{ running ? '回归中…' : '运行回归' }}
        </button>
      </div>
      <div v-if="error" class="form-err">{{ error }}</div>
    </div>
  </div>

  <template v-if="summary">
    <div class="cards">
      <div class="card">
        <div class="k">整体结果</div>
        <div class="v"><span class="badge" :class="summary.passed ? 'b-pass' : 'b-fail'"><span class="dot"></span>{{ summary.passed ? '全部通过' : '存在失败' }}</span></div>
      </div>
      <div class="card"><div class="k">通过率</div><div class="v pass">{{ passRate }}%</div></div>
      <div class="card"><div class="k">通过 / 总数</div><div class="v pri">{{ summary.passed_count }}<span class="sub"> / {{ summary.total }}</span></div></div>
      <div class="card"><div class="k">接口覆盖率</div><div class="v">{{ coverage }}%<span class="sub"> ({{ summary.interface_covered }}/{{ summary.interface_total }})</span></div></div>
    </div>

    <div class="panel">
      <div class="panel-head">用例明细<span class="count">共 {{ summary.results?.length || 0 }} 条</span></div>
      <div v-if="!summary.results?.length" class="state">本次回归没有匹配到用例</div>
      <template v-else>
        <div class="row head">
          <span class="c-id">用例</span>
          <span class="c-res">结果</span>
          <span class="c-note">说明</span>
        </div>
        <div v-for="r in summary.results" :key="r.case_id" class="row">
          <span class="c-id"><span class="id">#{{ r.case_id }}</span></span>
          <span class="c-res"><span class="badge" :class="r.passed ? 'b-pass' : 'b-fail'"><span class="dot"></span>{{ r.passed ? '通过' : '失败' }}</span></span>
          <span class="c-note">{{ r.error || '' }}</span>
        </div>
      </template>
    </div>
  </template>
</template>

<style scoped>
.run-panel { margin-bottom:24px; }
.run-body { padding:20px 22px; }
.hint { font-size:12.5px; color:var(--text-muted); margin-bottom:16px; line-height:1.6; }
.controls { display:flex; align-items:flex-end; gap:16px; flex-wrap:wrap; }
.field { display:flex; flex-direction:column; gap:8px; }
.field label { font-size:12.5px; font-weight:600; color:var(--text); }
.field label .opt { color:var(--text-muted); font-weight:400; }
.field input, .field select { height:38px; min-width:180px; padding:0 12px; font-size:13px; color:var(--text);
  background:var(--surface-2); border:1px solid var(--border); border-radius:8px; font-family:inherit; }
.field input:focus, .field select:focus { outline:none; border-color:var(--primary); }
.chk { display:flex; align-items:center; gap:7px; font-size:13px; color:var(--text); height:38px; cursor:pointer; }
.chk input { width:16px; height:16px; accent-color:var(--primary); }
.run-btn { height:38px; }
.spin { width:14px; height:14px; border:2px solid rgba(255,255,255,.4); border-top-color:#fff;
  border-radius:50%; animation:spin .7s linear infinite; }
@keyframes spin { to { transform:rotate(360deg); } }

.cards { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:24px; }
.card { background:var(--surface); border:1px solid var(--border);
  border-radius:14px; padding:18px 20px; box-shadow:var(--shadow-sm); }
.card .k { font-size:12px; color:var(--text-muted); margin-bottom:10px; font-weight:550; }
.card .v { font-size:27px; font-weight:780; letter-spacing:-.5px; }
.card .v.pass { color:var(--pass-fg); }
.card .v.pri { color:var(--primary); }
.card .v .sub { font-size:14px; font-weight:600; color:var(--text-muted); }

.row { display:grid; grid-template-columns:120px 100px 1fr; align-items:center; gap:12px;
  padding:13px 20px; border-bottom:1px solid var(--border); font-size:13px; }
.row:last-child { border-bottom:none; }
.row.head { font-size:11.5px; font-weight:600; color:var(--text-muted);
  text-transform:uppercase; letter-spacing:.5px; background:var(--surface-2); }
.c-id .id { color:var(--text-muted); font-family:ui-monospace,Consolas,monospace; font-size:12px;
  background:var(--surface-2); padding:2px 8px; border-radius:6px; }
.c-note { color:var(--fail-fg); font-size:12px; }

.state { padding:40px 20px; text-align:center; color:var(--text-muted); font-size:13px; }
.form-err { color:var(--fail-fg); font-size:12.5px; background:var(--fail-bg); padding:9px 12px; border-radius:8px; margin-top:14px; }

@media (max-width:1100px) {
  .cards { grid-template-columns:repeat(2,1fr); }
}
@media (max-width:640px) {
  .cards { grid-template-columns:1fr; gap:12px; }
  .controls { flex-direction:column; align-items:stretch; }
  .field input, .field select { min-width:0; }
}
</style>
