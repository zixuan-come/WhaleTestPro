<template>
  <div class="test-suites">
    <div class="top-bar">
      <div class="suite-heading">
        <h2>测试套件</h2>
        <span class="suite-count">共 {{ suites.length }} 个</span>
      </div>
      <button @click="openCreate" class="btn btn-primary btn-create">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 5v14M5 12h14" />
        </svg>
        新建套件
      </button>
    </div>

    <section class="suite-list-panel" aria-label="测试套件列表">
      <div class="suite-list-toolbar">
        <label class="suite-search">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></svg>
          <input v-model="search" aria-label="搜索套件名称或简介" placeholder="搜索套件名称、简介…" />
        </label>
        <span v-if="search.trim()" class="search-count" role="status">找到 {{ filteredSuites.length }} 个套件</span>
      </div>
      <div v-if="loadingSuites" class="suite-list-state" role="status">正在加载套件…</div>
      <div v-else-if="suiteLoadError" class="suite-list-state error" role="alert">{{ suiteLoadError }}<button class="btn btn-ghost" @click="fetchSuites">重试</button></div>
      <template v-else-if="filteredSuites.length">
        <table class="suite-table">
          <thead><tr><th scope="col">套件名称</th><th scope="col">内容组成</th><th scope="col">更新时间</th><th scope="col" class="actions-column">操作</th></tr></thead>
          <tbody>
            <tr v-for="suite in pageSuites" :key="suite.id" class="suite-row">
              <td class="suite-info"><strong :title="suite.name">{{ suite.name }}</strong><span class="suite-description" :title="suite.description || '暂无简介'">{{ suite.description || '暂无简介' }}</span></td>
              <td class="suite-composition" data-label="内容组成"><span>{{ composition(suite) }}</span></td>
              <td class="suite-updated" data-label="更新时间"><time v-if="suite.updated_at || suite.created_at" :datetime="suite.updated_at || suite.created_at" :title="formatDate(suite.updated_at || suite.created_at)">{{ formatDate(suite.updated_at || suite.created_at) }}</time><span v-else>—</span></td>
              <td class="suite-row-actions">
                <button type="button" class="suite-text-button run" @click="runSuite(suite.id)" :disabled="running" :aria-label="'运行套件：' + suite.name">运行</button>
                <button type="button" class="suite-text-button" @click="editSuite(suite)" :aria-label="'编辑套件：' + suite.name">编辑</button>
                <details class="suite-more" @keydown.esc.stop.prevent="$event.currentTarget.open = false">
                  <summary :aria-label="'更多操作：' + suite.name" @click="closeOtherMenus($event)"><svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="1.8" /><circle cx="12" cy="12" r="1.8" /><circle cx="19" cy="12" r="1.8" /></svg></summary>
                  <div class="suite-more-menu"><button type="button" @click="requestDelete(suite, $event)">删除套件</button></div>
                </details>
              </td>
            </tr>
          </tbody>
        </table>
        <div class="suite-pagination"><span>共 {{ filteredSuites.length }} 个 · 每页 {{ pageSize }} 个</span><div><button type="button" class="btn btn-ghost" :disabled="page <= 1" @click="page--" aria-label="上一页套件">上一页</button><span aria-live="polite">{{ page }} / {{ pageCount }}</span><button type="button" class="btn btn-ghost" :disabled="page >= pageCount" @click="page++" aria-label="下一页套件">下一页</button></div></div>
      </template>
      <div v-else class="empty-state">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>
        <p>{{ suites.length ? '没有匹配的套件' : '还没有测试套件' }}</p>
        <button v-if="suites.length" type="button" class="btn btn-ghost" @click="search = ''">清空搜索</button>
        <button v-else @click="openCreate" class="btn btn-primary btn-create-empty">创建第一个套件</button>
      </div>
    </section>

    <!-- 创建/编辑对话框 -->
    <Modal v-if="showCreateDialog || showEditDialog" :title="showEditDialog ? '编辑套件' : '新建套件'" :max-width="960" :busy="saving" hide-scrollbar @close="closeDialog">
      <form id="suite-editor-form" class="suite-editor-form" @submit.prevent="submitForm">
        <fieldset :disabled="saving" class="suite-editor-fields">
        <div class="suite-basic-fields">
        <div class="form-row">
          <label class="required">套件名称</label>
          <input v-model="form.name" required maxlength="100" placeholder="如: 每日冒烟测试" />
        </div>
        <div class="form-row">
          <label>描述</label>
          <textarea v-model="form.description" maxlength="500" rows="2" placeholder="描述这个套件的用途（可选）"></textarea>
        </div>
        </div>
        <SuiteContentPicker v-model="selection" :disabled="saving" @ready="pickerReady = $event" />
        <p v-if="saveError" class="suite-save-error" role="alert">{{ saveError }}</p>
        </fieldset>
      </form>
      <template #foot><span class="suite-selection-count">已选 {{ selection.scenario_ids.length }} 个场景、{{ selection.case_ids.length }} 个独立用例</span><button type="button" @click="closeDialog" class="btn btn-ghost" :disabled="saving">取消</button><button type="submit" form="suite-editor-form" class="btn btn-primary" :disabled="saving || !pickerReady">{{ saving ? '保存中…' : showEditDialog ? '保存修改' : '创建套件' }}</button></template>
    </Modal>

    <!-- 运行对话框 -->
    <Modal v-if="showRunDialog" title="运行套件" :max-width="400" :busy="running" @close="showRunDialog = false">
      <div>
        <div class="form-row">
          <label>选择环境</label>
          <select v-model="selectedEnvId" :disabled="running || environmentsLoading">
            <option :value="null" disabled>请选择执行环境</option>
            <option v-for="env in environments" :key="env.id" :value="env.id">
              {{ env.name }}
            </option>
          </select>
          <p v-if="!canExecuteRun" class="run-environment-note" role="status">{{ runEnvironmentMessage }} <RouterLink v-if="!environmentsLoading && !environmentsError && !environments.length" to="/environments">前往环境管理</RouterLink><button v-if="environmentsError" type="button" class="btn btn-ghost" @click="fetchEnvironments">重试</button></p>
        </div>
        <div class="form-actions">
          <button @click="showRunDialog = false" class="btn-cancel" :disabled="running">取消</button>
          <button @click="executeRun" class="btn-submit" :disabled="running || !canExecuteRun">{{ running ? '正在执行…' : '开始执行' }}</button>
        </div>
      </div>
    </Modal>

    <!-- 运行结果 -->
    <Modal v-if="runResult" title="运行结果" :max-width="600" hide-scrollbar @close="runResult = null">
      <SuiteRunResult :result="runResult" />
      <template #foot><button type="button" class="btn btn-primary" @click="runResult = null">关闭</button></template>
    </Modal>
  </div>
</template>

<script>
import { listSuites, createSuite, updateSuite, deleteSuite as apiDeleteSuite, runSuite as apiRunSuite } from '../api/suite';
import { listEnvironments } from '../api/environment';
import Modal from '../components/Modal.vue';
import SuiteContentPicker from '../components/SuiteContentPicker.vue';
import SuiteRunResult from '../components/SuiteRunResult.vue';
import { useAuthStore } from '../stores/auth';
import { showMessage, confirmAction } from '../composables/feedback';

export default {
  name: 'TestSuites',
  components: { Modal, SuiteContentPicker, SuiteRunResult },
  data() {
    return {
      suites: [],
      search: '', page: 1, pageSize: 20, loadingSuites: false, suiteLoadError: '',
      running: false, runVersion: 0,
      environments: [], environmentsLoading: false, environmentsError: '',
      showCreateDialog: false,
      showEditDialog: false,
      showRunDialog: false,
      editingId: null,
      selectedEnvId: null,
      runningSuiteId: null,
      runResult: null,
      form: {
        name: '',
        description: '',
      },
      selection: { scenario_ids: [], case_ids: [] },
      pickerReady: false, saving: false, saveError: '',
      suitesVersion: 0, envVersion: 0, saveVersion: 0,
    };
  },
  mounted() {
    document.addEventListener('pointerdown', this.closeMenusOutside);
    this.fetchSuites();
    this.fetchEnvironments();
  },
  computed: {
    runEnvironment() { return this.environments.find(env => String(env.id) === String(this.selectedEnvId ?? '')) || null; },
    canExecuteRun() { return !this.environmentsLoading && !this.environmentsError && Boolean(this.runEnvironment); },
    runEnvironmentMessage() { return this.environmentsLoading ? '正在加载执行环境…' : this.environmentsError || (this.environments.length ? '请选择有效的执行环境后再运行。' : '当前项目暂无执行环境，请先在环境管理中创建。'); },
    filteredSuites() { const query = this.search.trim().toLocaleLowerCase(); return this.suites.filter(suite => !query || `${suite.name || ''} ${suite.description || ''}`.toLocaleLowerCase().includes(query)); },
    pageCount() { return Math.max(1, Math.ceil(this.filteredSuites.length / this.pageSize)); },
    pageSuites() { return this.filteredSuites.slice((this.page - 1) * this.pageSize, this.page * this.pageSize); },
    projectIdentity() { const auth = useAuthStore(); return `${auth.username}:${auth.currentProjectId}:${auth.token}`; },
  },
  watch: {
    search() { this.page = 1; this.closeMenusOutside(); },
    page() { this.closeMenusOutside(); },
    pageCount(value) { this.page = Math.min(this.page, value); },
    projectIdentity() {
      this.runVersion++; this.running = false; this.runningSuiteId = null; this.search = ''; this.page = 1;
      this.saveVersion++; this.saving = false; this.closeDialog();
      this.showRunDialog = false; this.runResult = null; this.suites = []; this.environments = []; this.selectedEnvId = null; this.environmentsError = '';
      this.fetchSuites(); this.fetchEnvironments();
    },
  },
  beforeUnmount() { document.removeEventListener('pointerdown', this.closeMenusOutside); this.suitesVersion++; this.envVersion++; this.saveVersion++; this.runVersion++; },
  methods: {
    openCreate() { if (this.saving) return; this.closeDialog(); this.showCreateDialog = true; },
    async fetchSuites() {
      const version = ++this.suitesVersion, context = this.projectIdentity;
      this.loadingSuites = true; this.suiteLoadError = '';
      try {
        const data = [];
        for (let skip = 0; ; skip += 100) {
          const batch = await listSuites({ skip, limit: 100 });
          if (version !== this.suitesVersion || context !== this.projectIdentity) return;
          if (!Array.isArray(batch)) throw Error('套件数据格式异常');
          data.push(...batch);
          if (batch.length < 100) break;
        }
        if (version !== this.suitesVersion || context !== this.projectIdentity) return;
        // 兜底成数组:模板里 suites.length / filter 依赖数组,拿到非数组会整页崩(白屏)
        this.suites = Array.isArray(data) ? data : [];
      } catch (error) {
        if (version === this.suitesVersion && context === this.projectIdentity) this.suiteLoadError = '获取套件列表失败：' + (error.message || '未知错误');
      } finally { if (version === this.suitesVersion) this.loadingSuites = false; }
    },
    async fetchEnvironments() {
      const version = ++this.envVersion, context = this.projectIdentity;
      this.environmentsLoading = true; this.environmentsError = '';
      try {
        const data = await listEnvironments();
        if (version !== this.envVersion || context !== this.projectIdentity) return;
        if (!Array.isArray(data)) throw Error('环境数据格式异常');
        this.environments = data;
        const auth = useAuthStore(), preferred = auth.getPreferredEnv?.(auth.currentProjectId);
        if (preferred && !data.some(env => String(env.id) === String(preferred))) auth.setPreferredEnv?.(auth.currentProjectId, '');
        if (!this.runEnvironment) this.selectedEnvId = this.showRunDialog && preferred && data.some(env => String(env.id) === String(preferred)) ? preferred : null;
      } catch (error) {
        if (version === this.envVersion && context === this.projectIdentity) this.environmentsError = '获取执行环境失败，请重试。';
      } finally { if (version === this.envVersion && context === this.projectIdentity) this.environmentsLoading = false; }
    },
    async submitForm() {
      if (this.saving || !this.pickerReady) return;
      this.saveError = '';
      if (!this.form.name.trim()) { this.saveError = '请填写套件名称'; return; }
      if (this.selection.scenario_ids.length > 100 || this.selection.case_ids.length > 100) { this.saveError = '最多选择 100 个场景、100 个独立用例'; return; }
      const context = this.projectIdentity, version = ++this.saveVersion;
      const payload = {
        name: this.form.name.trim(),
        description: this.form.description?.trim() || null,
        scenario_ids: this.selection.scenario_ids.length ? [...this.selection.scenario_ids] : null,
        case_ids: this.selection.case_ids.length ? [...this.selection.case_ids] : null,
      };
      this.saving = true;
      try {
        if (this.showEditDialog) {
          await updateSuite(this.editingId, payload);
          if (version !== this.saveVersion || context !== this.projectIdentity) return;
          showMessage('套件更新成功', 'success');
        } else {
          // Compatibility with the existing API; suite content is unrestricted.
          await createSuite({ ...payload, type: 'mixed' });
          if (version !== this.saveVersion || context !== this.projectIdentity) return;
          showMessage('套件创建成功', 'success');
        }

        this.saving = false; this.closeDialog();
        this.fetchSuites();
      } catch (error) {
        if (version === this.saveVersion && context === this.projectIdentity) this.saveError = error.message || '保存失败，请重试';
      } finally { if (version === this.saveVersion) this.saving = false; }
    },
    editSuite(suite) {
      if (this.saving) return;
      this.editingId = suite.id;
      this.form.name = suite.name;
      this.form.description = suite.description || '';
      this.selection = { scenario_ids: [...(suite.scenario_ids || [])], case_ids: [...(suite.case_ids || [])] };
      this.pickerReady = false; this.saveError = '';
      this.showEditDialog = true;
    },
    async deleteSuite(id) {
      const context = this.projectIdentity;
      if (!await confirmAction('删除后无法恢复，请确认是否删除此套件。', '删除套件')) return;
      if (context !== this.projectIdentity) return;
      try {
        await apiDeleteSuite(id);
        if (context !== this.projectIdentity) return;
        showMessage('删除成功', 'success');
        this.fetchSuites();
      } catch (error) {
        if (context !== this.projectIdentity) return;
        showMessage('删除失败: ' + (error.message || '未知错误'), 'error');
      }
    },
    runSuite(id) {
      if (this.running) return;
      this.runningSuiteId = id;
      const auth = useAuthStore(), preferred = auth.getPreferredEnv?.(auth.currentProjectId);
      this.selectedEnvId = preferred && this.environments.some(env => String(env.id) === String(preferred)) ? preferred : null;
      this.showRunDialog = true;
    },
    async executeRun() {
      if (this.running || this.runningSuiteId == null) return;
      if (!this.canExecuteRun) { showMessage(this.runEnvironmentMessage, 'error'); return; }
      const version = ++this.runVersion, context = this.projectIdentity;
      const envId = this.runEnvironment.id, auth = useAuthStore();
      auth.setPreferredEnv?.(auth.currentProjectId, String(envId));
      this.running = true;
      try {
        const result = await apiRunSuite(this.runningSuiteId, envId);
        if (version !== this.runVersion || context !== this.projectIdentity) return;
        this.runResult = result;
        this.showRunDialog = false;
      } catch (error) {
        if (version !== this.runVersion || context !== this.projectIdentity) return;
        showMessage('运行失败: ' + (error.message || '未知错误'), 'error');
      } finally { if (version === this.runVersion) this.running = false; }
    },
    closeDialog() {
      if (this.saving) return;
      this.showCreateDialog = false;
      this.showEditDialog = false;
      this.editingId = null;
      this.form = { name: '', description: '' };
      this.selection = { scenario_ids: [], case_ids: [] };
      this.pickerReady = false; this.saveError = '';
    },
    composition(suite) {
      return [suite.scenario_ids?.length ? suite.scenario_ids.length + ' 场景' : '', suite.case_ids?.length ? suite.case_ids.length + ' 独立用例' : ''].filter(Boolean).join(' · ') || '空套件';
    },
    closeMenusOutside(event) {
      if (typeof document === 'undefined') return;
      document.querySelectorAll('.suite-more[open]').forEach(menu => { if (!event || !menu.contains(event.target)) menu.open = false; });
    },
    closeOtherMenus(event) { document.querySelectorAll('.suite-more[open]').forEach(menu => { if (menu !== event.currentTarget.parentElement) menu.open = false; }); },
    requestDelete(suite, event) { event.currentTarget.closest('details').open = false; this.deleteSuite(suite.id); },
    formatDate(dateStr) {
      if (!dateStr) return '—';
      const d = new Date(dateStr);
      return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString('zh-CN', { year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', hour12:false });
    },
  },
};
</script>

<style scoped>
.run-environment-note{margin:8px 0 0;color:var(--text-muted);font-size:12px;line-height:1.6}
.suite-editor-form { height:min(570px,calc(88dvh - 170px)); min-height:330px; }
.suite-editor-fields { height:100%;min-width:0;min-height:0;padding:0;margin:0;border:0;display:flex;flex-direction:column;gap:14px; }
.suite-basic-fields { display:grid;grid-template-columns:1fr 1.35fr;gap:16px;flex:none; }
.suite-basic-fields .form-row { margin:0; }.suite-basic-fields .form-row label { font-size:12px;margin-bottom:6px; }
.suite-basic-fields .form-row input { height:36px;padding:7px 10px;font-size:13px; }
.suite-basic-fields .form-row textarea { font:inherit;font-size:12px;line-height:1.5;resize:none;height:54px;padding:7px 10px;scrollbar-width:none; }
.suite-basic-fields textarea::-webkit-scrollbar { display:none; }
.suite-selection-count { margin-right:auto;align-self:center;font-size:11px;color:var(--text-muted);line-height:1.7; }
.suite-save-error { font-size:12px;color:var(--fail-fg);margin:0;flex:none; }
@media(max-width:680px) { .suite-basic-fields { grid-template-columns:1fr;gap:8px; }.suite-basic-fields .form-row textarea { height:36px; }.suite-editor-form { height:calc(88dvh - 190px);min-height:350px; }.suite-selection-count { flex-basis:100%; }.suite-editor-form :deep(.suite-picker) { min-height:0; } }
.test-suites {
  padding: 24px;
  max-width: 1800px;
  margin: 0 auto;
}

/* 顶部栏 */
.top-bar {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
}

.top-bar h2 {
  font-size: 28px;
  font-weight: 700;
  color: var(--text);
  margin: 0;
}

.suite-heading {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.suite-count {
  padding: 3px 10px;
  border: 1px solid var(--border);
  border-radius: 99px;
  background: var(--surface-2);
  color: var(--text-muted);
  font-size: 12px;
  white-space: nowrap;
}

/* 紧凑套件列表 */
.suite-list-panel { background:var(--surface);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow-sm); }
.suite-list-toolbar { display:flex;align-items:center;gap:14px;padding:16px 20px;border-bottom:1px solid var(--border); }
.suite-search { display:flex;align-items:center;gap:9px;width:340px;max-width:100%;padding:0 11px;height:36px;border:1px solid var(--border);border-radius:7px;background:var(--surface-2); }
.suite-search:focus-within { border-color:var(--primary);box-shadow:0 0 0 3px var(--ring); }
.suite-search svg { width:15px;height:15px;flex:none;color:var(--text-muted); }
.suite-search input { border:0;outline:none;min-width:0;width:100%;background:transparent;color:var(--text);font:inherit;font-size:13px; }
.search-count,.suite-list-state { font-size:12px;color:var(--text-muted); }
.suite-list-state { padding:40px 20px;display:flex;justify-content:center;align-items:center;gap:12px;flex-wrap:wrap; }.suite-list-state.error { color:var(--fail-fg); }
.suite-table { width:100%;table-layout:fixed;border-collapse:collapse;text-align:left;font-size:13px; }
.suite-table th { font-size:12px;color:var(--text-muted);font-weight:500;background:var(--surface-2);padding:11px 20px; }
.suite-table th:first-child { width:38%; }.suite-table th:nth-child(2) { width:25%; }.suite-table th:nth-child(3) { width:21%; }.suite-table th:last-child { width:16%; }
.suite-table td { padding:9px 20px;border-top:1px solid var(--border);vertical-align:middle; }
.suite-row:hover { background:var(--surface-2); }
.suite-info strong { display:block;font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:1.6; }
.suite-description { display:block;margin-top:2px;font-size:12px;color:var(--text-muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:1.5; }
.suite-composition { font-size:12px;line-height:1.7;overflow-wrap:anywhere; }.suite-updated { font-size:12px;color:var(--text-muted);font-variant-numeric:tabular-nums; }
.suite-table .actions-column { text-align:right; }.suite-table .suite-row-actions { text-align:right;white-space:nowrap; }
.suite-text-button { border:0;background:none;color:var(--primary);font:inherit;font-size:12px;padding:6px;cursor:pointer;border-radius:5px; }.suite-text-button:hover { background:var(--ring); }.suite-text-button:disabled { opacity:.45;cursor:wait; }
.suite-more { position:relative;display:inline-block;text-align:left;vertical-align:middle; }
.suite-more > summary { display:grid;place-items:center;width:28px;height:28px;border-radius:5px;color:var(--text-muted);list-style:none;cursor:pointer; }.suite-more > summary::-webkit-details-marker { display:none; }.suite-more > summary svg { width:17px;height:17px; }.suite-more[open] > summary,.suite-more > summary:hover { background:var(--ring);color:var(--primary); }
.suite-more-menu { position:absolute;right:0;top:calc(100% + 5px);z-index:5;width:112px;padding:5px;background:var(--surface);border:1px solid var(--border);border-radius:8px;box-shadow:var(--shadow-md); }.suite-more-menu button { width:100%;padding:8px;border:0;border-radius:4px;background:none;color:var(--fail-fg);font:inherit;font-size:12px;cursor:pointer;text-align:left; }.suite-more-menu button:hover { background:var(--fail-bg); }
.suite-text-button:focus-visible,.suite-more summary:focus-visible,.suite-more-menu button:focus-visible { outline:2px solid var(--primary);outline-offset:2px; }
.suite-pagination { display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;border-top:1px solid var(--border);padding:12px 20px;font-size:12px;color:var(--text-muted); }.suite-pagination > div { display:flex;align-items:center;gap:12px; }.suite-pagination .btn { height:28px;padding:0 10px;font-size:12px; }.suite-pagination button:disabled { opacity:.4;cursor:default; }
.empty-state { display:flex;flex-direction:column;align-items:center;justify-content:center;padding:60px 20px;color:var(--text-muted); }.empty-state svg { width:44px;height:44px;margin-bottom:12px;opacity:.4; }.empty-state p { font-size:13px;margin-bottom:16px; }
@media(max-width:1100px) { .suite-table th,.suite-table td { padding-left:14px;padding-right:14px; }.suite-table th:first-child { width:34%; }.suite-table th:nth-child(2) { width:25%; }.suite-table th:nth-child(3) { width:22%; }.suite-table th:last-child { width:19%; } }
@media(max-width:700px) {
 .test-suites { padding:16px 12px; }.top-bar h2 { font-size:24px; }.top-bar { margin-bottom:16px; }
 .suite-list-toolbar { padding:12px;flex-wrap:wrap;gap:8px; }.suite-search { width:100%; }.suite-table thead { position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%); }
 .suite-table,.suite-table tbody { display:block; }.suite-table .suite-row { display:grid;grid-template-columns:minmax(0,1fr) auto;padding:10px 12px;gap:8px;position:relative;border-top:1px solid var(--border); }.suite-table .suite-row:first-child { border-top:0; }
 .suite-table td { display:block;border:0;padding:0;min-width:0; }.suite-info { grid-column:1;grid-row:1; }.suite-row-actions { grid-column:2;grid-row:1;align-self:start; }.suite-composition,.suite-updated { grid-column:1 / -1;font-size:11px; }.suite-composition::before,.suite-updated::before { content:attr(data-label);display:inline-block;width:68px;color:var(--text-muted); }
 .suite-pagination { padding:12px;gap:10px; }.suite-pagination > div { margin-left:auto;gap:8px; }
}

/* 对话框 */
.form-row {
  margin-bottom: 20px;
}

.form-row label {
  display: block;
  font-size: 14px;
  font-weight: 500;
  color: var(--text);
  margin-bottom: 8px;
}

.form-row label.required::after {
  content: ' *';
  color: #d63031;
}

.form-row .hint {
  font-size: 12px;
  font-weight: 400;
  color: var(--text-muted);
  margin-left: 4px;
}

.form-row input,
.form-row textarea,
.form-row select {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 14px;
  color: var(--text);
  background: var(--bg);
  transition: all 0.2s;
}

.form-row input:focus,
.form-row textarea:focus,
.form-row select:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 24px;
}

.btn-cancel,
.btn-submit {
  padding: 10px 20px;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-cancel {
  background: var(--bg);
  color: var(--text);
}

.btn-cancel:hover {
  background: var(--border);
}

.btn-submit {
  background: var(--primary);
  color: white;
}

.btn-submit:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
}

button:disabled { cursor:default;opacity:.5; }
</style>
