<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useAuthStore } from '../stores/auth'
import { regressionOptions, previewRegression, runSelectedRegression } from '../api/regression'
import { useExecutionEnvironment } from '../composables/executionEnvironment'
import EnvironmentSelect from '../components/EnvironmentSelect.vue'
import { regressionRows } from '../utils/regression'

const auth = useAuthStore()
const { envs, selectedEnv, loadEnvironments } = useExecutionEnvironment()
const mode = ref('suite'), selectedIds = ref([]), search = ref(''), tagFilter = ref('')
const catalog = ref({ suites: [], cases: [] }), loading = ref(false), loadError = ref('')
const plan = ref(null), previewing = ref(false), previewError = ref(''), running = ref(false), runError = ref('')
const summary = ref(null), notify = ref(false)
const resultsPanel = ref(null)
let optionsVersion = 0, previewVersion = 0, runVersion = 0, previewTimer
const projectKey = computed(() => `${auth.username}:${auth.currentProjectId}:${auth.token}`)
const source = computed(() => mode.value === 'suite' ? catalog.value.suites : catalog.value.cases)
const tags = computed(() => [...new Set(catalog.value.cases.flatMap(item => item.tags || []))].sort())
const visible = computed(() => source.value.filter(item =>
  (!search.value.trim() || `${item.name} ${item.interface_name || ''}`.toLowerCase().includes(search.value.trim().toLowerCase())) &&
  (mode.value !== 'case' || !tagFilter.value || item.tags?.includes(tagFilter.value))))
const selection = computed(() => ({ mode: mode.value, ids: [...selectedIds.value], env_id: selectedEnv.value ? Number(selectedEnv.value) : null }))
const selectionKey = computed(() => JSON.stringify(selection.value))
const rows = computed(() => regressionRows(summary.value?.results || []).sort((a, b) => Number(a.passed) - Number(b.passed)))
const canRun = computed(() => !!auth.token && !!auth.currentProjectId && !loading.value && !loadError.value && !running.value && !previewing.value && !!plan.value?.ready && !previewError.value)

async function loadOptions() {
  const version = ++optionsVersion, context = projectKey.value
  catalog.value = { suites: [], cases: [] }; loadError.value = ''; loading.value = true
  if (!auth.token || !auth.currentProjectId) { loading.value = false; return }
  const results = await Promise.allSettled([regressionOptions(), loadEnvironments()])
  if (version !== optionsVersion || context !== projectKey.value) return
  if (results[0].status === 'fulfilled') catalog.value = results[0].value
  else loadError.value = results[0].reason.message || '测试内容加载失败'
  if (results[1].status === 'rejected') loadError.value = '测试环境加载失败，请重试'
  loading.value = false
}
function changeMode(value) {
  if (running.value || mode.value === value) return
  mode.value = value; selectedIds.value = []; search.value = ''; tagFilter.value = ''
}
function toggle(id) {
  if (running.value) return
  selectedIds.value = selectedIds.value.includes(id) ? selectedIds.value.filter(value => value !== id) : [...selectedIds.value, id]
}
function selectVisible() { if (!running.value) selectedIds.value = [...new Set([...selectedIds.value, ...visible.value.map(item => item.id)])] }
function clearSelection() { if (!running.value) selectedIds.value = [] }
function invalidatePreview() {
  clearTimeout(previewTimer); previewVersion++; plan.value = null; previewError.value = ''; runError.value = ''
  previewing.value = selectedIds.value.length > 0
  if (selectedIds.value.length && auth.token && auth.currentProjectId) previewTimer = setTimeout(loadPreview, 200)
}
async function loadPreview() {
  clearTimeout(previewTimer)
  const version = ++previewVersion, context = projectKey.value, key = selectionKey.value
  if (!selectedIds.value.length) { previewing.value = false; return }
  previewing.value = true; previewError.value = ''; plan.value = null
  try {
    const result = await previewRegression(selection.value)
    if (version === previewVersion && context === projectKey.value && key === selectionKey.value) plan.value = result
  } catch (error) {
    if (version === previewVersion && context === projectKey.value) previewError.value = error.message || '执行清单加载失败'
  } finally { if (version === previewVersion) previewing.value = false }
}
async function onRun() {
  if (!canRun.value) return
  const version = ++runVersion, context = projectKey.value
  const request = { ...selection.value, preview_key: plan.value.preview_key, notify: notify.value }
  running.value = true; summary.value = null; runError.value = ''
  try {
    const result = await runSelectedRegression(request)
    if (version === runVersion && context === projectKey.value) {
      summary.value = result
      await nextTick()
      if (version === runVersion && context === projectKey.value) resultsPanel.value?.scrollIntoView({ block: 'start' })
    }
  } catch (error) {
    if (version !== runVersion || context !== projectKey.value) return
    runError.value = error.status === 409 ? '测试内容或环境已变更，已刷新清单，请确认后重新开始。'
      : '未能确认本次执行结果，请先到“测试报告 → 回归测试”查看，避免重复执行。' + (error.message ? `（${error.message}）` : '')
    if (error.status === 409 || error.status === 404 || error.status === 400) await loadPreview()
  } finally { if (version === runVersion) running.value = false }
}
function resetProject() {
  clearTimeout(previewTimer); previewVersion++; runVersion++
  selectedIds.value = []; search.value = ''; tagFilter.value = ''; plan.value = null; summary.value = null
  previewing.value = false; running.value = false; previewError.value = ''; runError.value = ''; notify.value = false
  loadOptions()
}
watch(selectionKey, invalidatePreview, { flush: 'sync' })
watch(projectKey, resetProject, { flush: 'sync' })
onMounted(loadOptions)
onBeforeUnmount(() => { clearTimeout(previewTimer); optionsVersion++; previewVersion++; runVersion++ })
</script>

<template>
  <p class="intro">代码更新后，重新执行已有测试，检查原有功能是否正常。</p>
  <div v-if="!auth.currentProjectId" class="panel state">请先选择项目。</div>
  <template v-else>
    <fieldset class="configuration" :disabled="running">
      <div class="panel setup-panel">
        <div class="panel-head"><span>1 · 选择测试内容</span><span class="step-note">先选环境，再选择本次要执行的测试</span></div>
        <div class="setup-body">
          <div class="environment-field"><span class="field-label">测试环境</span><EnvironmentSelect v-model="selectedEnv" :environments="envs" /></div>
          <div class="mode-switch" role="group" aria-label="测试内容选择方式">
            <button type="button" :aria-pressed="mode === 'suite'" :class="{ active: mode === 'suite' }" @click="changeMode('suite')">选择测试套件 <small>推荐</small></button>
            <button type="button" :aria-pressed="mode === 'case'" :class="{ active: mode === 'case' }" @click="changeMode('case')">手动选择用例</button>
          </div>
          <p class="selection-help">{{ mode === 'suite' ? '复用已经整理好的场景和用例，场景中的步骤会按顺序执行、传递变量。多个套件分别执行。' : '适合互不依赖的用例；需要前后传参的流程，请先整理成场景并加入套件。' }}</p>
          <div v-if="loading" class="state" role="status">正在加载测试内容…</div>
          <div v-else-if="loadError" class="state error" role="alert">{{ loadError }} <button class="btn btn-ghost" @click="loadOptions">重试</button></div>
          <template v-else>
            <div class="selection-toolbar"><input v-model="search" :aria-label="mode === 'suite' ? '搜索套件' : '搜索用例'" :placeholder="mode === 'suite' ? '搜索套件名称…' : '搜索用例或接口名称…'" /><span>已选 {{ selectedIds.length }} {{ mode === 'suite' ? '个套件' : '个用例' }}</span><button type="button" class="text-btn" :disabled="!visible.length" @click="selectVisible">全选当前结果</button><button type="button" class="text-btn" :disabled="!selectedIds.length" @click="clearSelection">清空</button></div>
            <details v-if="mode === 'case' && tags.length" class="tag-filter"><summary>按标签筛选<span v-if="tagFilter"> · {{ tagFilter }}</span></summary><div class="tag-options"><button type="button" :aria-pressed="!tagFilter" @click="tagFilter = ''">全部标签</button><button v-for="tag in tags" :key="tag" type="button" :aria-pressed="tagFilter === tag" @click="tagFilter = tag">{{ tag }}</button></div></details>
            <div v-if="!source.length" class="state empty">{{ mode === 'suite' ? '还没有测试套件，先把需要复用的场景和用例整理为一个套件。' : '还没有测试用例，请先在接口测试中创建。' }} <RouterLink :to="mode === 'suite' ? '/suites' : '/interfaces'">{{ mode === 'suite' ? '去创建套件' : '去创建用例' }}</RouterLink></div>
            <div v-else-if="!visible.length" class="state">没有匹配的测试内容，请调整筛选条件。</div>
            <div v-else class="selection-list">
              <label v-for="item in visible" :key="item.id" class="selection-row" :class="{ selected: selectedIds.includes(item.id) }"><input type="checkbox" :checked="selectedIds.includes(item.id)" @change="toggle(item.id)" /><span><strong>{{ item.name }}</strong><small v-if="item.description || item.interface_name">{{ item.description || item.interface_name }}</small><span v-if="mode === 'case' && item.tags?.length" class="item-tags">{{ item.tags.join(' · ') }}</span></span></label>
            </div>
          </template>
        </div>
      </div>
      <div class="panel plan-panel">
        <div class="panel-head">2 · 确认执行清单</div>
        <div v-if="!selectedIds.length" class="state">从上方选择测试套件或用例，这里会列出本次执行内容。</div>
        <div v-else-if="previewing" class="state" role="status">正在确认执行内容…</div>
        <div v-else-if="previewError" class="state error" role="alert">{{ previewError }} <button class="btn btn-ghost" @click="loadPreview">刷新清单</button></div>
        <div v-else-if="plan" class="plan-body">
          <div class="plan-counts"><span v-if="plan.suite_count">{{ plan.suite_count }} 个套件</span><span v-if="plan.scenario_count">{{ plan.scenario_count }} 个场景（{{ plan.step_count }} 个步骤）</span><span>{{ plan.case_count }} 个独立用例</span></div>
          <ul v-if="plan.warnings.length" class="warnings"><li v-for="warning in plan.warnings" :key="warning">{{ warning }}</li></ul>
          <div class="plan-list"><div v-for="group in plan.groups" :key="group.id" class="plan-group"><strong>{{ group.name }}</strong><ul v-if="group.items"><li v-for="(item, index) in group.items" :key="index"><span class="item-kind">{{ item.type === 'scenario' ? '场景' : '用例' }}</span>{{ item.name }}<ol v-if="item.steps?.length" class="step-chain"><li v-for="(step, stepIndex) in item.steps" :key="stepIndex">{{ stepIndex + 1 }}. {{ step.name }}</li></ol></li></ul></div></div>
        </div>
        <div class="run-footer"><details class="notify-options"><summary>通知设置</summary><label><input v-model="notify" type="checkbox" /> 执行完成后发送飞书通知</label><small>需已配置飞书 Webhook</small></details><button type="button" class="btn btn-primary" :disabled="!canRun" @click="onRun">{{ running ? '正在执行…' : '开始回归' }}</button></div>
      </div>
    </fieldset>
    <p v-if="running" class="running-note" role="status">正在执行本次测试，请等待结果。执行记录会保存在“测试报告 → 回归测试”。</p>
    <p v-if="runError" class="run-error" role="alert">{{ runError }} <RouterLink :to="{ path: '/reports', query: { kind: 'regression' } }">查看回归报告</RouterLink></p>
    <div v-if="summary" ref="resultsPanel" class="panel results-panel" aria-live="polite">
      <div class="panel-head"><span>执行结果</span><RouterLink class="btn btn-ghost" :to="{ path: '/reports', query: { kind: 'regression', report: summary.report_id } }">查看完整报告</RouterLink></div>
      <div class="result-summary"><strong :class="summary.passed ? 'pass' : 'fail'">{{ summary.passed ? '全部通过' : '存在失败' }}</strong><span class="pass">通过 {{ summary.passed_count }} 项</span><span class="fail">失败 {{ summary.failed_count }} 项</span></div>
      <p v-if="summary.notification_warning" class="notification-warning">{{ summary.notification_warning }}</p>
      <div v-for="(row, index) in rows" :key="index" class="result-row"><span class="badge" :class="row.passed ? 'b-pass' : 'b-fail'">{{ row.passed ? '通过' : '失败' }}</span><div><strong>{{ row.name }}</strong><small v-if="row.suite_name">所属套件：{{ row.suite_name }}</small><p v-if="!row.passed" class="failure-reason">{{ row.reason }}</p></div></div>
      <details class="more-stats"><summary>更多统计</summary><p>通过率 {{ Math.round(summary.pass_rate * 100) }}% · 接口覆盖率 {{ Math.round(summary.interface_coverage * 100) }}%（{{ summary.interface_covered }}/{{ summary.interface_total }}）</p><small>执行项按场景或独立用例统计；接口覆盖率按关联到的接口数量统计。</small></details>
    </div>
  </template>
</template>

<style scoped>
.intro{margin-bottom:18px;color:var(--text-muted);font-size:13px;line-height:1.7}.configuration{padding:0;margin:0;min-width:0;border:0}.configuration:disabled{opacity:.8}.setup-panel,.plan-panel{margin-bottom:20px}.panel-head{gap:12px;flex-wrap:wrap}.step-note{font-size:12px;font-weight:400;color:var(--text-muted)}.setup-body,.plan-body{padding:18px 20px}.field-label{font-size:13px;font-weight:600}.environment-field{display:flex;align-items:center;gap:16px;margin-bottom:18px}.environment-field :deep(.env-select){width:290px}.mode-switch{display:flex;gap:6px;flex-wrap:wrap}.mode-switch button{border:1px solid var(--border);padding:9px 14px;border-radius:7px;background:var(--surface);color:var(--text-muted);font:inherit;font-size:13px;cursor:pointer}.mode-switch button.active{border-color:var(--primary);background:var(--surface-2);color:var(--primary)}.mode-switch small{margin-left:6px;font-size:10px}.selection-help{font-size:12px;line-height:1.7;color:var(--text-muted);margin:12px 0 16px}.selection-toolbar{display:flex;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:12px}.selection-toolbar>input{flex:1;min-width:180px;max-width:420px;height:34px;border:1px solid var(--border);border-radius:6px;padding:0 10px;background:var(--surface-2);color:var(--text);font:inherit;font-size:12px}.selection-toolbar>span{font-size:12px;color:var(--text-muted)}.text-btn{padding:4px;border:0;background:transparent;color:var(--primary);font:inherit;font-size:12px;cursor:pointer}.text-btn:disabled{opacity:.4;cursor:default}.selection-list{max-height:310px;overflow:auto;border:1px solid var(--border);border-radius:8px}.selection-row{display:flex;align-items:flex-start;gap:12px;padding:13px 14px;border-bottom:1px solid var(--border);cursor:pointer}.selection-row:last-child{border:0}.selection-row.selected{background:var(--surface-2)}input[type=checkbox]{accent-color:var(--primary);flex:none;margin-top:3px;width:15px;height:15px}.selection-row>span{min-width:0;overflow-wrap:anywhere}.selection-row strong,.plan-group>strong,.result-row strong{font-size:13px;font-weight:600;overflow-wrap:anywhere}.selection-row small,.result-row small,.item-tags{display:block;margin-top:5px;font-size:11px;color:var(--text-muted);line-height:1.6}.tag-filter{margin-bottom:12px}.tag-filter summary,.notify-options summary,.more-stats summary{font-size:12px;color:var(--text-muted);cursor:pointer}.tag-options{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}.tag-options button{padding:5px 9px;border:1px solid var(--border);border-radius:5px;background:var(--surface);color:var(--text-muted);font:inherit;font-size:12px;cursor:pointer}.tag-options button[aria-pressed=true]{border-color:var(--primary);color:var(--primary)}.state{padding:28px 16px;text-align:center;font-size:13px;color:var(--text-muted);line-height:1.8}.state a{color:var(--primary);white-space:nowrap}.error,.run-error,.failure-reason{color:var(--fail-fg)}.plan-counts{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:14px;font-size:12px;color:var(--text-muted)}.plan-list{max-height:380px;overflow:auto}.plan-group{padding:12px;border:1px solid var(--border);border-radius:7px;margin-bottom:10px}.plan-group:last-child{margin-bottom:0}.plan-group ul{margin:10px 0 0;padding-left:20px;font-size:12px;line-height:1.8}.plan-group ul>li{padding:5px 0;overflow-wrap:anywhere}.item-kind{margin-right:8px;color:var(--text-muted);font-size:11px}.step-chain{display:flex;flex-wrap:wrap;gap:6px 18px;list-style:none;padding:5px 0 0 0;margin:0;color:var(--text-muted);font-size:11px}.warnings,.run-error,.notification-warning{padding:12px 16px;background:var(--fail-bg);color:var(--fail-fg);border-radius:7px;font-size:12px;line-height:1.8;overflow-wrap:anywhere}.warnings{padding-left:30px;margin-bottom:12px}.run-footer{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:14px 20px;border-top:1px solid var(--border)}.notify-options label{display:flex;gap:7px;align-items:center;margin-top:10px;font-size:12px}.notify-options small{display:block;font-size:11px;margin-top:5px;color:var(--text-muted)}.running-note{margin:12px 0 18px;color:var(--text-muted);font-size:13px}.run-error{margin-bottom:18px}.result-summary{display:flex;align-items:center;flex-wrap:wrap;gap:18px;padding:20px;font-size:13px}.pass{color:var(--pass-fg)}.fail{color:var(--fail-fg)}.result-row{display:flex;align-items:flex-start;gap:12px;padding:14px 20px;border-top:1px solid var(--border)}.result-row>div{min-width:0}.result-row>.badge{flex:none}.failure-reason{font-size:12px;line-height:1.7;margin-top:6px;overflow-wrap:anywhere}.more-stats{padding:16px 20px;border-top:1px solid var(--border)}.more-stats p{margin-top:12px;font-size:12px}.more-stats small{display:block;margin-top:7px;font-size:11px;color:var(--text-muted)}button:focus-visible,input:focus-visible,a:focus-visible,summary:focus-visible{outline:2px solid var(--primary);outline-offset:2px}button:disabled{cursor:default}@media(max-width:600px){.setup-body,.plan-body{padding:14px}.step-note{display:none}.environment-field{align-items:stretch;flex-direction:column;gap:9px}.environment-field :deep(.env-select){width:100%}.selection-toolbar>input{flex-basis:100%;max-width:none}.mode-switch button{flex:1;padding:9px 10px}.run-footer{padding:14px}.result-row{padding:14px}.result-summary{padding:16px}.panel-head .btn{font-size:12px}}
</style>
