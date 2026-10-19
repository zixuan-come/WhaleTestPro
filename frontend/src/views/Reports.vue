<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { listExecutionReports, listReportFolders, createReportFolder, renameReportFolder, deleteReportFolder, moveExecutionReports, deleteExecutionReports, deleteExecutionReport } from '../api/report'
import { useAuthStore } from '../stores/auth'
import { useFeedback } from '../composables/feedback'
import { formatShanghaiDateTime } from '../utils/time'
import { preferredReportType, rememberReportType, REPORT_TYPES } from '../utils/reportPreferences'
import ReportExecutionDetail from '../components/ReportExecutionDetail.vue'
import Modal from '../components/Modal.vue'
import SuiteFilterSelect from '../components/SuiteFilterSelect.vue'

const auth = useAuthStore(), route = useRoute()
const { notice, showMessage, confirmAction, resolveConfirm } = useFeedback()
const linkedReportId = ref(null), reportType = ref('all'), items = ref([]), page = ref(1), pageSize = ref(20)
const totalPages = ref(0), reportTotal = ref(0), passedTotal = ref(0), failedTotal = ref(0), runningTotal = ref(0), passRateTotal = ref(0)
const statusFilter = ref('all'), search = ref(''), dateFrom = ref(''), dateTo = ref('')
const loading = ref(false), error = ref(''), openId = ref(null)
const folders = ref([]), allCount = ref(0), unfiledCount = ref(0), selectedFolder = ref('all')
const folderLoading = ref(false), folderError = ref(''), canManage = ref(false)
const folderCollapsed = ref(globalThis.matchMedia?.('(max-width:1050px)').matches ?? false)
const chosen = ref(new Map()), folderForm = ref(null), formError = ref(''), moveForm = ref(null), moveTarget = ref('')
const mutating = ref(false), confirming = ref(false), busy = computed(() => mutating.value || confirming.value)
let loadVersion = 0, folderVersion = 0, mutationVersion = 0, searchTimer, disposed = false
const projectKey = computed(() => `${auth.username}:${auth.currentProjectId}:${auth.token}`)
const currentLabel = computed(() => REPORT_TYPES.find(type => type.value === reportType.value)?.label || '')
const folderLabel = computed(() => selectedFolder.value === 'all' ? '全部报告' : selectedFolder.value === '0' ? '未归档' : folders.value.find(folder => String(folder.id) === selectedFolder.value)?.name || '报告目录')
const pageStart = computed(() => reportTotal.value ? (page.value - 1) * pageSize.value + 1 : 0)
const pageEnd = computed(() => Math.min(page.value * pageSize.value, reportTotal.value))
const filtered = computed(() => !!(search.value.trim() || statusFilter.value !== 'all' || dateFrom.value || dateTo.value))
const chosenIds = computed(() => [...chosen.value.keys()])
const pageChosen = computed(() => items.value.length > 0 && items.value.every(item => chosen.value.has(item.id)))
const pagePartlyChosen = computed(() => !pageChosen.value && items.value.some(item => chosen.value.has(item.id)))
const chosenRunning = computed(() => [...chosen.value.values()].some(isRunning))
const destinations = computed(() => [{ value: '0', label: '未归档' }, ...folders.value.map(folder => ({ value: String(folder.id), label: folder.name }))])
const sourceLabel = value => ({ manual: '手动执行', scheduled: '定时任务' }[value] || '未记录')
const typeLabel = value => REPORT_TYPES.find(type => type.value === value)?.label || value
function duration(value) { return value == null ? '未记录' : value < 1 ? '< 1 ms' : value < 1000 ? `${value} ms` : `${(value / 1000).toFixed(2)} s` }
function isRunning(report) { return report.passed == null || ['running', 'queued', 'pending'].includes(report.status) }
function validContext(context) { return !disposed && context === projectKey.value }
function clearSelection() { chosen.value = new Map() }

async function load(targetPage = 1) {
  clearTimeout(searchTimer)
  const version = ++loadVersion, context = projectKey.value
  if (!auth.token || !auth.currentProjectId) {
    items.value = []; reportTotal.value = passedTotal.value = failedTotal.value = runningTotal.value = passRateTotal.value = 0
    page.value = 1; totalPages.value = 0; loading.value = false; error.value = ''; openId.value = null; return
  }
  loading.value = true; error.value = ''; openId.value = null
  try {
    const data = await listExecutionReports({ kind: reportType.value, page: targetPage, page_size: pageSize.value,
      folder_id: selectedFolder.value === 'all' ? undefined : Number(selectedFolder.value),
      q: search.value.trim() || undefined, status: statusFilter.value,
      date_from: dateFrom.value || undefined, date_to: dateTo.value || undefined })
    if (version !== loadVersion || !validContext(context)) return
    if (!Array.isArray(data?.items)) throw Error('报告数据格式错误')
    if (data.total_pages && targetPage > data.total_pages) return await load(data.total_pages)
    items.value = data.items; page.value = data.total ? data.page : 1; totalPages.value = data.total_pages
    reportTotal.value = data.total; passedTotal.value = data.passed_count; failedTotal.value = data.failed_count
    runningTotal.value = data.running_count; passRateTotal.value = data.pass_rate
    for (const item of data.items) if (chosen.value.has(item.id)) chosen.value.set(item.id, item)
  } catch (e) { if (version === loadVersion && validContext(context)) error.value = e.message || '加载报告失败' }
  finally { if (version === loadVersion) loading.value = false }
}
async function loadFolders() {
  const version = ++folderVersion, context = projectKey.value
  if (!auth.token || !auth.currentProjectId) return
  folderLoading.value = true; folderError.value = ''
  try {
    const data = await listReportFolders()
    if (version !== folderVersion || !validContext(context)) return
    if (!Array.isArray(data?.items)) throw Error('目录数据格式错误')
    folders.value = data.items; allCount.value = data.total; unfiledCount.value = data.unfiled; canManage.value = data.can_manage === true
    if (!canManage.value) { clearSelection(); folderForm.value = null; moveForm.value = null }
    if (!['all', '0'].includes(selectedFolder.value) && !data.items.some(folder => String(folder.id) === selectedFolder.value)) {
      selectedFolder.value = '0'; clearSelection(); await load(1)
    }
  } catch (e) { if (version === folderVersion && validContext(context)) { folderError.value = e.message || '加载目录失败'; canManage.value = false; clearSelection() } }
  finally { if (version === folderVersion) folderLoading.value = false }
}
function switchType(type) {
  if (type === reportType.value || busy.value) return
  linkedReportId.value = null; reportType.value = type; clearSelection()
  rememberReportType(auth.username, auth.currentProjectId, type); load(1)
}
function selectFolder(value) {
  if (busy.value || selectedFolder.value === String(value)) return
  selectedFolder.value = String(value); linkedReportId.value = null; clearSelection(); load(1)
}
function resetFilters() { search.value = ''; statusFilter.value = 'all'; dateFrom.value = ''; dateTo.value = ''; clearSelection(); load(1) }
function filtersChanged() { clearSelection(); load(1) }
function searchChanged() { clearSelection(); clearTimeout(searchTimer); searchTimer = setTimeout(() => load(1), 250) }
function changePage(target) { if (!busy.value && target >= 1 && target <= totalPages.value && target !== page.value) load(target) }
async function refresh() { await Promise.all([load(page.value), loadFolders()]) }
function restore() {
  mutationVersion++; folderVersion++; mutating.value = false
  if (confirming.value) resolveConfirm(false)
  confirming.value = false; folderForm.value = null; moveForm.value = null; clearSelection()
  folders.value = []; allCount.value = unfiledCount.value = 0; canManage.value = false; folderLoading.value = false; folderError.value = ''
  selectedFolder.value = 'all'; linkedReportId.value = null; reportType.value = preferredReportType(auth.username, auth.currentProjectId)
  resetFilters(); loadFolders()
}
function initialize() {
  if (['regression', 'suite'].includes(route.query.kind)) {
    reportType.value = route.query.kind; rememberReportType(auth.username, auth.currentProjectId, route.query.kind)
    linkedReportId.value = /^run-[1-9]\d*$/.test(route.query.report || '') ? route.query.report : null
    search.value = typeof route.query.q === 'string' ? route.query.q.trim().slice(0, 100) : ''
    load(1); loadFolders()
  } else restore()
}
function tabKey(event, index) {
  const count = REPORT_TYPES.length, next = { ArrowLeft: (index + count - 1) % count, ArrowRight: (index + 1) % count, Home: 0, End: count - 1 }[event.key]
  if (next == null) return
  event.preventDefault(); const type = REPORT_TYPES[next].value; switchType(type)
  nextTick(() => document.getElementById(`report-tab-${type}`)?.focus())
}
function toggleReport(report) {
  if (busy.value || !canManage.value) return
  if (chosen.value.has(report.id)) chosen.value.delete(report.id)
  else if (chosen.value.size >= 500) showMessage('一次最多选择 500 份报告', 'error')
  else chosen.value.set(report.id, report)
}
function togglePage() {
  if (busy.value || !canManage.value) return
  if (pageChosen.value) items.value.forEach(report => chosen.value.delete(report.id))
  else {
    const added = items.value.filter(report => !chosen.value.has(report.id))
    if (chosen.value.size + added.length > 500) { showMessage('一次最多选择 500 份报告', 'error'); return }
    added.forEach(report => chosen.value.set(report.id, report))
  }
}
async function ask(message, title) {
  if (!canManage.value || busy.value) return false
  notice.value = null
  const context = projectKey.value, version = mutationVersion; confirming.value = true
  try { return await confirmAction(message, title) && validContext(context) && version === mutationVersion }
  finally { if (validContext(context) && version === mutationVersion) confirming.value = false }
}
async function perform(action, onDone, form = false) {
  if (!canManage.value || busy.value) return
  const context = projectKey.value, version = ++mutationVersion; mutating.value = true
  try {
    const result = await action()
    if (!validContext(context) || version !== mutationVersion) return
    onDone(result); clearSelection(); await refresh()
  } catch (e) {
    if (validContext(context) && version === mutationVersion) {
      if (form) formError.value = e.message || '保存目录失败'
      else showMessage(e.message || '操作失败，请刷新后重试', 'error')
    }
  } finally { if (validContext(context) && version === mutationVersion) mutating.value = false }
}
function editFolder(folder = null) {
  if (!canManage.value || busy.value) return
  const date = formatShanghaiDateTime(new Date().toISOString()).slice(0, 10)
  folderForm.value = { id: folder?.id ?? null, name: folder?.name ?? `${date}-${auth.username}` }; formError.value = ''
}
async function saveFolder() {
  if (!folderForm.value || !canManage.value || busy.value) return
  const { id, name } = folderForm.value, clean = name.trim()
  if (!clean || [...clean].length > 100) { formError.value = '请填写 1～100 个字符的目录名称'; return }
  formError.value = ''
  await perform(() => id == null ? createReportFolder({ name: clean }) : renameReportFolder(id, { name: clean }), saved => {
    folderForm.value = null; if (id == null) selectedFolder.value = String(saved.id)
    showMessage(id == null ? '目录已创建' : '目录已更新')
  }, true)
}
async function removeFolder(folder) {
  const id = folder.id
  if (!await ask(`删除目录“${folder.name}”？其中的报告将移回“未归档”，报告内容保留。`, '删除报告目录')) return
  await perform(() => deleteReportFolder(id), () => {
    if (selectedFolder.value === String(id)) selectedFolder.value = '0'
    showMessage('目录已删除，报告已保留')
  })
}
function openMove(ids) {
  if (!canManage.value || busy.value || !ids.length) return
  moveForm.value = { ids: [...ids] }; moveTarget.value = ''
}
async function saveMove() {
  if (!moveForm.value || moveTarget.value === '') return
  const ids = [...moveForm.value.ids], folder_id = moveTarget.value === '0' ? null : Number(moveTarget.value)
  await perform(() => moveExecutionReports({ report_ids: ids, folder_id }), result => {
    moveForm.value = null; showMessage(`已移动 ${result.moved} 份报告`)
  })
}
async function removeReports(reports) {
  if (!reports.length || reports.some(isRunning)) return
  const ids = reports.map(report => report.id)
  if (!await ask(`确认删除这 ${ids.length} 份报告及其执行明细？接口、用例、场景和套件配置会保留，报告删除后无法恢复。`, '删除测试报告')) return
  await perform(() => ids.length === 1 ? deleteExecutionReport(ids[0]) : deleteExecutionReports({ report_ids: ids }), result => {
    linkedReportId.value = null; showMessage(`已删除 ${result.deleted} 份报告`)
  })
}
watch(projectKey, restore, { flush: 'sync' })
onMounted(initialize)
onBeforeUnmount(() => { disposed = true; loadVersion++; folderVersion++; mutationVersion++; clearTimeout(searchTimer); if (confirming.value) resolveConfirm(false) })
</script>

<template>
  <div class="report-location"><button type="button" class="btn btn-ghost btn-sm" :aria-expanded="!folderCollapsed" aria-controls="report-directories" @click="folderCollapsed = !folderCollapsed"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M3 7V5h7l2 2h9v13H3Z" /></svg>{{ folderCollapsed ? '显示目录' : '收起目录' }}</button><strong :title="folderLabel">{{ folderLabel }}</strong><span>按项目共享</span></div>
  <div class="report-layout" :class="{ collapsed: folderCollapsed }">
    <aside v-if="!folderCollapsed" id="report-directories" class="directory-panel panel" aria-label="报告目录">
      <div class="directory-heading"><strong>报告目录</strong><button v-if="canManage" class="icon-button" type="button" title="新建目录" aria-label="新建报告目录" :disabled="busy" @click="editFolder()"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg></button></div>
      <div class="directory-builtins"><button type="button" :class="{ active: selectedFolder === 'all' }" :disabled="busy" @click="selectFolder('all')"><span>全部报告</span><small>{{ folderLoading ? '—' : allCount }}</small></button><button type="button" :class="{ active: selectedFolder === '0' }" :disabled="busy" @click="selectFolder('0')"><span>未归档</span><small>{{ folderLoading ? '—' : unfiledCount }}</small></button></div>
      <div class="directory-section">自定义目录</div><p v-if="folderError" class="directory-message error" role="alert">{{ folderError }}<button class="text-button" @click="loadFolders">重试</button></p><p v-else-if="folderLoading && !folders.length" class="directory-message">加载中…</p><p v-else-if="!folders.length" class="directory-message">暂无目录{{ canManage ? '，点击上方 ＋ 创建。' : '。' }}</p>
      <div class="directory-list"><div v-for="folder in folders" :key="folder.id" class="directory-entry" :class="{ active: selectedFolder === String(folder.id) }"><button type="button" class="directory-name" :title="folder.name" :disabled="busy" @click="selectFolder(folder.id)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M3 7V5h7l2 2h9v13H3Z" /></svg><span>{{ folder.name }}</span><small>{{ folder.count }}</small></button><div v-if="canManage" class="directory-actions"><button type="button" class="icon-button" :aria-label="`重命名目录 ${folder.name}`" title="重命名目录" :disabled="busy" @click="editFolder(folder)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="m16 3 5 5-12 12-6 1 1-6Z" /></svg></button><button type="button" class="icon-button danger" :aria-label="`删除目录 ${folder.name}`" title="删除目录并保留报告" :disabled="busy" @click="removeFolder(folder)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" /></svg></button></div></div></div>
    </aside>
    <section class="reports-content">
      <div class="report-tabs" role="tablist" aria-label="报告类型"><button v-for="(type, index) in REPORT_TYPES" :id="`report-tab-${type.value}`" :key="type.value" type="button" role="tab" :disabled="busy" :aria-selected="reportType === type.value" :tabindex="reportType === type.value ? 0 : -1" aria-controls="report-panel" :class="{ active: reportType === type.value }" @click="switchType(type.value)" @keydown="tabKey($event, index)">{{ type.label }}</button></div>
      <div class="cards"><div class="card"><span>报告总数</span><strong>{{ loading ? '—' : reportTotal }}</strong></div><div class="card"><span>通过</span><strong class="pass">{{ loading ? '—' : passedTotal }}</strong></div><div class="card"><span>失败</span><strong class="fail">{{ loading ? '—' : failedTotal }}</strong></div><div class="card"><span title="通过报告数 ÷ 当前筛选条件下的报告总数">报告通过率</span><strong>{{ loading ? '—' : Math.round(passRateTotal * 100) + '%' }}</strong></div></div>
      <div v-if="linkedReportId && auth.token && auth.currentProjectId" class="panel linked-report"><div class="panel-head">本次回归报告<button class="btn btn-ghost" @click="linkedReportId = null">关闭明细</button></div><ReportExecutionDetail :key="`${projectKey}-${linkedReportId}`" :report-id="linkedReportId" /></div>
      <div id="report-panel" class="panel reports-panel" :class="{ managed: canManage }" role="tabpanel" :aria-labelledby="`report-tab-${reportType}`">
        <div class="panel-head"><div>{{ currentLabel }}报告 <span class="count">共 {{ loading ? '—' : reportTotal }} 条</span><span v-if="!loading && runningTotal" class="running-count">{{ runningTotal }} 条执行中</span></div><button class="btn btn-ghost" :disabled="loading || busy" @click="refresh">刷新</button></div>
        <fieldset class="report-filters" :disabled="busy"><input v-model="search" aria-label="搜索报告名称" maxlength="100" placeholder="搜索名称…" @input="searchChanged" /><label>状态<select v-model="statusFilter" @change="filtersChanged"><option value="all">全部</option><option value="passed">通过</option><option value="failed">失败</option></select></label><label>执行日期<input v-model="dateFrom" type="date" aria-label="开始日期" @change="filtersChanged" /></label><span class="date-divider">至</span><input v-model="dateTo" type="date" aria-label="结束日期" @change="filtersChanged" /><button v-if="filtered" class="btn btn-ghost" @click="resetFilters">重置</button></fieldset>
        <div v-if="!auth.currentProjectId" class="state">请先选择项目。</div><div v-else-if="loading" class="state" role="status">正在加载报告…</div><div v-else-if="error" class="state error" role="alert">{{ error }} <button class="btn btn-ghost" @click="load(1)">重试</button></div><div v-else-if="!items.length" class="state">{{ filtered ? '未找到符合条件的报告。' : selectedFolder !== 'all' ? '这个目录还没有报告，可在其他目录中选择报告并移动至此。' : '暂无报告，执行后会在这里显示结果。' }}</div>
        <template v-else>
          <div class="report-row head"><label v-if="canManage" class="report-check"><input type="checkbox" aria-label="选择本页全部报告" :checked="pageChosen" :indeterminate="pagePartlyChosen" :disabled="busy" @change="togglePage" /></label><span>结果</span><span>名称</span><span class="kind">类型</span><span class="duration">耗时</span><span class="source">来源</span><span class="environment">环境</span><span class="time">执行时间</span><span class="action-heading">操作</span></div>
          <template v-for="report in items" :key="report.id"><div class="report-row" :class="{ open: openId === report.id }"><label v-if="canManage" class="report-check"><input type="checkbox" :aria-label="`选择报告 ${report.name}`" :checked="chosen.has(report.id)" :disabled="busy" @change="toggleReport(report)" /></label><span><span class="badge" :class="report.passed == null ? 'b-skip' : report.passed ? 'b-pass' : 'b-fail'">{{ report.passed == null ? '执行中' : report.passed ? '通过' : '失败' }}</span></span><button type="button" class="report-name" :title="report.name" :aria-expanded="openId === report.id" @click="openId = openId === report.id ? null : report.id"><span>{{ report.name }}</span><small v-if="report.historical">历史记录</small></button><span class="kind">{{ typeLabel(report.kind) }}</span><span class="duration">{{ duration(report.duration_ms) }}</span><span class="source">{{ sourceLabel(report.trigger_source) }}</span><span class="environment" :title="report.environment_name || '未记录'">{{ report.environment_name || '未记录' }}</span><span class="time">{{ formatShanghaiDateTime(report.created_at) }}</span><div class="row-actions"><template v-if="canManage"><button type="button" class="icon-button" title="移动到目录" :aria-label="`移动报告 ${report.name}`" :disabled="busy" @click="openMove([report.id])"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M3 7V5h7l2 2h9v13H3Zm6 7h8m-3-3 3 3-3 3" /></svg></button><button type="button" class="icon-button danger" :title="isRunning(report) ? '执行中的报告不能删除' : '删除报告'" :aria-label="`删除报告 ${report.name}`" :disabled="busy || isRunning(report)" @click="removeReports([report])"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" /></svg></button></template><button type="button" class="icon-button" :aria-label="`${openId === report.id ? '收起' : '查看'}报告 ${report.name}`" :aria-expanded="openId === report.id" @click="openId = openId === report.id ? null : report.id"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true" :class="{ up: openId === report.id }"><path d="m6 9 6 6 6-6" /></svg></button></div></div><ReportExecutionDetail v-if="openId === report.id" :key="`${projectKey}-${report.id}`" :report-id="report.id" /></template>
        </template>
        <div v-if="canManage && chosenIds.length" class="bulk-actions"><span>已选 {{ chosenIds.length }} 份<span v-if="chosenRunning">（含执行中报告）</span></span><button type="button" class="text-button" :disabled="busy" @click="clearSelection">取消选择</button><div><button type="button" class="btn btn-ghost" :disabled="busy" @click="openMove(chosenIds)">移动到目录</button><button type="button" class="btn btn-ghost delete-button" :disabled="busy || chosenRunning" :title="chosenRunning ? '请取消选择执行中的报告后再删除' : '删除选中报告'" @click="removeReports([...chosen.values()])">批量删除</button></div></div>
        <div v-if="!loading && !error && reportTotal" class="pagination"><span>显示 {{ pageStart }}–{{ pageEnd }} 条</span><label>每页<select v-model.number="pageSize" :disabled="busy" @change="load(1)"><option :value="10">10</option><option :value="20">20</option><option :value="50">50</option><option :value="100">100</option></select></label><button class="btn btn-ghost" :disabled="busy || page <= 1" @click="changePage(page - 1)">上一页</button><span>{{ page }} / {{ totalPages }}</span><button class="btn btn-ghost" :disabled="busy || page >= totalPages" @click="changePage(page + 1)">下一页</button></div>
      </div>
    </section>
  </div>
  <Modal v-if="folderForm" :title="folderForm.id == null ? '新建报告目录' : '重命名报告目录'" :max-width="460" :busy="mutating" @close="folderForm = null"><form id="report-folder-form" @submit.prevent="saveFolder"><label class="modal-label" for="report-folder-name">目录名称</label><input id="report-folder-name" v-model="folderForm.name" class="modal-input" maxlength="100" autocomplete="off" placeholder="例如：2026-10-20-张三" :disabled="mutating" /><p class="modal-hint">目录在当前项目内共享，可以收纳不同类型的测试报告。</p><p v-if="formError" class="form-error" role="alert">{{ formError }}</p></form><template #foot><button class="btn btn-ghost" :disabled="mutating" @click="folderForm = null">取消</button><button class="btn btn-primary" type="submit" form="report-folder-form" :disabled="mutating">{{ mutating ? '保存中…' : '保存目录' }}</button></template></Modal>
  <Modal v-if="moveForm" title="移动报告到目录" :max-width="460" :busy="mutating" @close="moveForm = null"><p class="modal-hint">将选中的 {{ moveForm.ids.length }} 份报告移动至：</p><SuiteFilterSelect v-model="moveTarget" :options="destinations" label="目标报告目录" input-id="report-move-folder" :disabled="mutating || folderLoading" /><p class="modal-hint">选择“未归档”可移出当前目录。</p><template #foot><button class="btn btn-ghost" :disabled="mutating" @click="moveForm = null">取消</button><button class="btn btn-primary" :disabled="mutating || moveTarget === ''" @click="saveMove">{{ mutating ? '移动中…' : '确认移动' }}</button></template></Modal>
</template>

<style scoped>
.report-location{display:flex;align-items:center;gap:12px;margin-bottom:14px;min-width:0}.report-location strong{font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}.report-location>span{flex:none;font-size:11px;color:var(--text-muted)}.report-location .btn{flex:none}.report-location svg{width:15px;height:15px}.report-layout{display:grid;grid-template-columns:220px minmax(0,1fr);gap:18px;align-items:start}.report-layout.collapsed{grid-template-columns:minmax(0,1fr)}.reports-content{container-type:inline-size;min-width:0}.directory-panel{position:sticky;top:20px;min-width:0;overflow:hidden}.directory-heading{display:flex;align-items:center;justify-content:space-between;padding:13px 12px;border-bottom:1px solid var(--border);font-size:13px}.directory-builtins{padding:8px;border-bottom:1px solid var(--border)}.directory-builtins button,.directory-name{display:flex;align-items:center;gap:7px;border:0;border-radius:6px;background:none;color:var(--text);font:inherit;font-size:12px;text-align:left;cursor:pointer;min-width:0}.directory-builtins button{width:100%;padding:10px}.directory-builtins span,.directory-name span{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}.directory-builtins small,.directory-name small{flex:none;font-size:11px;color:var(--text-muted)}.directory-section{padding:14px 12px 7px;font-size:11px;color:var(--text-muted)}.directory-list{max-height:calc(100vh - 330px);overflow:auto;scrollbar-width:thin;scrollbar-color:var(--border) transparent;padding:0 6px 8px;min-height:0}.directory-entry{display:flex;align-items:center;gap:2px;border-radius:6px;margin-bottom:3px}.directory-entry.active,.directory-builtins .active{background:var(--surface-2);color:var(--primary)}.directory-entry.active .directory-name{color:var(--primary)}.directory-name{flex:1;padding:10px 5px}.directory-name svg{flex:none;width:15px;height:15px}.directory-actions,.row-actions{display:flex;gap:1px;align-items:center;justify-content:flex-end}.directory-message{margin:0;padding:8px 12px 15px;color:var(--text-muted);font-size:12px;line-height:1.7;overflow-wrap:anywhere}.directory-message .text-button{display:block;margin-top:5px}.icon-button{display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;padding:6px;background:none;border:0;border-radius:5px;color:var(--text-muted);cursor:pointer;flex:none}.icon-button svg{width:15px;height:15px}.icon-button:hover{background:var(--surface-2);color:var(--primary)}.icon-button.danger:hover{background:var(--fail-bg);color:var(--fail-fg)}button:disabled{opacity:.45;cursor:not-allowed}.icon-button svg.up{transform:rotate(180deg)}button:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid var(--primary);outline-offset:1px}.text-button{padding:0;border:0;background:none;color:var(--primary);font:inherit;font-size:12px;cursor:pointer}
.linked-report{margin-bottom:20px}.report-tabs{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:16px;padding:4px;width:fit-content;border:1px solid var(--border);border-radius:8px;background:var(--surface)}.report-tabs button{padding:8px 13px;border:0;border-radius:5px;background:transparent;color:var(--text-muted);font:inherit;font-size:12px;cursor:pointer}.report-tabs button.active{color:#fff;background:var(--primary)}.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:16px}.card{min-width:0;padding:12px 16px;background:var(--surface);border:1px solid var(--border);border-radius:12px}.card>span{display:block;margin-bottom:6px;color:var(--text-muted);font-size:12px;line-height:18px}.card strong{display:block;font-size:24px;line-height:1.2;font-weight:700;font-variant-numeric:tabular-nums}.card .pass{color:var(--pass-fg)}.card .fail{color:var(--fail-fg)}.panel-head{flex-wrap:wrap;gap:10px}.panel-head .count,.running-count{margin-left:9px;color:var(--text-muted);font-size:11px;font-weight:400}.report-filters{display:flex;align-items:center;flex-wrap:wrap;gap:10px;padding:12px 16px;margin:0;min-width:0;border:0;border-bottom:1px solid var(--border)}.report-filters label,.pagination label{display:flex;align-items:center;gap:6px;color:var(--text-muted);font-size:12px}input,select{height:32px;min-width:0;border:1px solid var(--border);border-radius:5px;padding:0 9px;background:var(--surface-2);color:var(--text);font:inherit;font-size:12px}.report-filters>input:first-child{width:180px}.date-divider{color:var(--text-muted);font-size:12px}
.report-row{display:grid;grid-template-columns:64px minmax(120px,1fr) 72px 65px 70px 90px 135px 28px;align-items:center;gap:8px;width:100%;padding:12px 16px;border-bottom:1px solid var(--border);background:var(--surface);color:var(--text);font-size:12px}.managed .report-row{grid-template-columns:26px 64px minmax(120px,1fr) 72px 65px 70px 90px 135px 88px}.report-row:not(.head):hover,.report-row.open{background:var(--surface-2)}.report-row.head{color:var(--text-muted);background:var(--surface-2);font-size:11px}.report-check{display:flex;align-items:center;justify-content:center}.report-check input{width:14px;height:14px;margin:0;padding:0;accent-color:var(--primary);cursor:pointer}.report-name{display:flex;flex-direction:column;align-items:flex-start;gap:3px;min-width:0;padding:0;background:none;border:0;color:var(--text);font:inherit;font-weight:600;text-align:left;cursor:pointer}.report-name>span{max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.report-name small{color:var(--text-muted);font-size:10px;font-weight:400}.kind,.duration,.source,.environment,.time{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text-muted);font-size:11px}.action-heading{text-align:right}.state{padding:36px 16px;color:var(--text-muted);font-size:13px;text-align:center}.state.error,.error{color:var(--fail-fg)}.pagination{display:flex;flex-wrap:wrap;justify-content:flex-end;align-items:center;gap:10px;padding:14px 16px;color:var(--text-muted);font-size:12px}.bulk-actions{display:flex;flex-wrap:wrap;align-items:center;gap:10px;padding:12px 16px;border-top:1px solid var(--border);background:var(--surface-2);font-size:12px;color:var(--text-muted)}.bulk-actions>div{display:flex;gap:8px;margin-left:auto}.delete-button{color:var(--fail-fg)}.modal-label{display:block;font-size:13px;margin-bottom:8px}.modal-input{width:100%;box-sizing:border-box;height:38px}.modal-hint{margin:12px 0;color:var(--text-muted);font-size:12px;line-height:1.7}.form-error{color:var(--fail-fg);background:var(--fail-bg);padding:9px 10px;border-radius:6px;font-size:12px}
@container(max-width:1000px){.environment,.source{display:none}.report-row{grid-template-columns:64px minmax(100px,1fr) 68px 65px 130px 28px}.managed .report-row{grid-template-columns:26px 60px minmax(100px,1fr) 68px 65px 130px 88px}}
@container(max-width:760px){.time,.duration{display:none}.report-row{grid-template-columns:64px minmax(90px,1fr) 68px 28px}.managed .report-row{grid-template-columns:24px 60px minmax(90px,1fr) 68px 88px}.cards{gap:8px}.card{padding:11px 12px}.card>span{font-size:11px}.report-filters{gap:8px}.report-filters>input:first-child{width:160px}}
@container(max-width:520px){.cards{grid-template-columns:repeat(2,minmax(0,1fr))}.report-tabs{width:100%;gap:2px}.report-tabs button{flex:1;padding:7px 4px;font-size:11px}.report-filters>input:first-child{width:100%}.report-filters input[type=date]{width:120px}.pagination{justify-content:center}.bulk-actions>div{margin-left:0}.report-row,.managed .report-row{padding:11px 10px;gap:5px}.managed .report-row{grid-template-columns:22px 56px minmax(60px,1fr) 58px 84px}}
@container(max-width:440px){.kind{display:none}.report-row{grid-template-columns:60px minmax(60px,1fr) 28px}.managed .report-row{grid-template-columns:22px 56px minmax(55px,1fr) 84px}.report-row .badge{font-size:10px;padding:3px 6px}}
@media(max-width:1050px){.report-layout{grid-template-columns:minmax(0,1fr)}.directory-panel{position:static}.directory-list{max-height:180px}.report-location>span{display:none}}
</style>
