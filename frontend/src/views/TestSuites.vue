<template>
  <div class="test-suites">
    <div class="top-bar">
      <h2>测试套件</h2>
      <button @click="showCreateDialog = true" class="btn-create">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 5v14M5 12h14" />
        </svg>
        新建套件
      </button>
    </div>

    <!-- 统计卡片区域 -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-icon total">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
          </svg>
        </div>
        <div class="stat-info">
          <div class="stat-label">总套件数</div>
          <div class="stat-value">{{ suites.length }}</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon scenario">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 6h4v4H4zM16 6h4v4h-4zM10 14h4v4h-4z" />
          </svg>
        </div>
        <div class="stat-info">
          <div class="stat-label">场景套件</div>
          <div class="stat-value">{{ typeCount('scenario') }}</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon case">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M9 11l3 3L22 4M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" />
          </svg>
        </div>
        <div class="stat-info">
          <div class="stat-label">用例套件</div>
          <div class="stat-value">{{ typeCount('case') }}</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon mixed">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 6h16M4 12h16M4 18h10" />
          </svg>
        </div>
        <div class="stat-info">
          <div class="stat-label">混合套件</div>
          <div class="stat-value">{{ typeCount('mixed') }}</div>
        </div>
      </div>
    </div>

    <!-- 套件卡片网格 - 一行5个 -->
    <div class="suites-grid">
      <div
        v-for="suite in suites"
        :key="suite.id"
        class="suite-card"
        :class="'suite-type-' + suite.type"
      >
        <div class="suite-header">
          <div class="suite-title">
            <h3>{{ suite.name }}</h3>
            <span :class="'type-badge type-' + suite.type">
              {{ typeLabel(suite.type) }}
            </span>
          </div>
          <div class="suite-actions">
            <button @click="runSuite(suite.id)" class="action-btn run" title="运行">
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M8 5v14l11-7z" />
              </svg>
            </button>
            <button @click="editSuite(suite)" class="action-btn edit" title="编辑">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4 12.5-12.5Z" />
              </svg>
            </button>
            <button @click="deleteSuite(suite.id)" class="action-btn delete" title="删除">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" />
              </svg>
            </button>
          </div>
        </div>

        <div class="suite-description">
          {{ suite.description || '暂无描述' }}
        </div>

        <div class="suite-stats">
          <div class="stat-item" v-if="suite.scenario_ids?.length">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M4 6h4v4H4z" />
            </svg>
            <span>{{ suite.scenario_ids.length }} 场景</span>
          </div>
          <div class="stat-item" v-if="suite.case_ids?.length">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M9 11l3 3L22 4" />
            </svg>
            <span>{{ suite.case_ids.length }} 用例</span>
          </div>
          <div class="stat-item" v-if="suite.tags?.length">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M7 7h.01M7 3h5l8 8-5 5-8-8V3z" />
            </svg>
            <span>{{ suite.tags.length }} 标签</span>
          </div>
          <div class="stat-item empty" v-if="!suite.scenario_ids?.length && !suite.case_ids?.length && !suite.tags?.length">
            <span>空套件</span>
          </div>
        </div>

        <div class="suite-footer">
          <div class="create-time">
            {{ formatDate(suite.created_at) }}
          </div>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-if="suites.length === 0" class="empty-state">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
        </svg>
        <p>还没有测试套件</p>
        <button @click="showCreateDialog = true" class="btn-create-empty">创建第一个套件</button>
      </div>
    </div>

    <!-- 创建/编辑对话框 -->
    <div v-if="showCreateDialog || showEditDialog" class="modal-overlay" @click.self="closeDialog">
      <div class="modal-dialog">
        <div class="modal-header">
          <h3>{{ showEditDialog ? '编辑套件' : '新建套件' }}</h3>
          <button @click="closeDialog" class="close-btn">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <form @submit.prevent="submitForm" class="modal-body">
          <div class="form-row">
            <label class="required">套件名称</label>
            <input v-model="form.name" required maxlength="100" placeholder="如: 每日冒烟测试" />
          </div>
          <div class="form-row">
            <label>描述</label>
            <textarea v-model="form.description" maxlength="500" rows="3" placeholder="描述这个套件的用途"></textarea>
          </div>
          <div class="form-row">
            <label class="required">套件类型</label>
            <div class="radio-group">
              <label class="radio-option">
                <input type="radio" v-model="form.type" value="scenario" />
                <span>场景套件</span>
              </label>
              <label class="radio-option">
                <input type="radio" v-model="form.type" value="case" />
                <span>用例套件</span>
              </label>
              <label class="radio-option">
                <input type="radio" v-model="form.type" value="mixed" />
                <span>混合套件</span>
              </label>
            </div>
          </div>
          <div class="form-row">
            <label>场景 ID <span class="hint">逗号分隔，如: 1,2,3</span></label>
            <input v-model="scenarioIdsText" placeholder="1,2,3" />
          </div>
          <div class="form-row">
            <label>用例 ID <span class="hint">逗号分隔，如: 10,11,12</span></label>
            <input v-model="caseIdsText" placeholder="10,11,12" />
          </div>
          <div class="form-row">
            <label>标签 <span class="hint">逗号分隔，如: smoke,p0</span></label>
            <input v-model="tagsText" placeholder="smoke,p0" />
          </div>
          <div class="form-actions">
            <button type="button" @click="closeDialog" class="btn-cancel">取消</button>
            <button type="submit" class="btn-submit">{{ showEditDialog ? '更新' : '创建' }}</button>
          </div>
        </form>
      </div>
    </div>

    <!-- 运行对话框 -->
    <div v-if="showRunDialog" class="modal-overlay" @click.self="showRunDialog = false">
      <div class="modal-dialog small">
        <div class="modal-header">
          <h3>运行套件</h3>
          <button @click="showRunDialog = false" class="close-btn">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div class="modal-body">
          <div class="form-row">
            <label>选择环境</label>
            <select v-model="selectedEnvId">
              <option :value="null">默认环境</option>
              <option v-for="env in environments" :key="env.id" :value="env.id">
                {{ env.name }}
              </option>
            </select>
          </div>
          <div class="form-actions">
            <button @click="showRunDialog = false" class="btn-cancel">取消</button>
            <button @click="executeRun" class="btn-submit">开始执行</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 运行结果 -->
    <div v-if="runResult" class="modal-overlay" @click.self="runResult = null">
      <div class="result-dialog">
        <div class="result-header">
          <h3>运行结果</h3>
          <button @click="runResult = null" class="close-btn">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div class="result-summary">
          <div class="result-stat">
            <div class="label">套件名称</div>
            <div class="value">{{ runResult.suite_name }}</div>
          </div>
          <div class="result-stat">
            <div class="label">执行时间</div>
            <div class="value">{{ runResult.duration_ms }}ms</div>
          </div>
          <div class="result-stat">
            <div class="label">总数</div>
            <div class="value">{{ runResult.total }}</div>
          </div>
          <div class="result-stat pass">
            <div class="label">通过</div>
            <div class="value">{{ runResult.passed }}</div>
          </div>
          <div class="result-stat fail">
            <div class="label">失败</div>
            <div class="value">{{ runResult.failed }}</div>
          </div>
          <div class="result-stat rate">
            <div class="label">通过率</div>
            <div class="value">{{ runResult.pass_rate }}%</div>
          </div>
        </div>
        <button @click="runResult = null" class="btn-close-result">关闭</button>
      </div>
    </div>
  </div>
</template>

<script>
import { listSuites, createSuite, updateSuite, deleteSuite as apiDeleteSuite, runSuite as apiRunSuite } from '../api/suite';
import { listEnvironments } from '../api/environment';

export default {
  name: 'TestSuites',
  data() {
    return {
      suites: [],
      environments: [],
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
        type: 'mixed',
      },
      scenarioIdsText: '',
      caseIdsText: '',
      tagsText: '',
    };
  },
  mounted() {
    this.fetchSuites();
    this.fetchEnvironments();
  },
  methods: {
    async fetchSuites() {
      try {
        const data = await listSuites();
        // 兜底成数组:模板里 suites.length / filter 依赖数组,拿到非数组会整页崩(白屏)
        this.suites = Array.isArray(data) ? data : [];
      } catch (error) {
        alert('获取套件列表失败: ' + (error.message || '未知错误'));
      }
    },
    async fetchEnvironments() {
      try {
        const data = await listEnvironments();
        this.environments = Array.isArray(data) ? data : [];
      } catch (error) {
        console.error('获取环境列表失败:', error);
      }
    },
    async submitForm() {
      const payload = {
        name: this.form.name.trim(),
        description: this.form.description?.trim() || null,
        type: this.form.type,
        scenario_ids: this.parseIds(this.scenarioIdsText),
        case_ids: this.parseIds(this.caseIdsText),
        tags: this.parseTags(this.tagsText),
      };

      try {
        if (this.showEditDialog) {
          await updateSuite(this.editingId, payload);
          alert('套件更新成功');
        } else {
          await createSuite(payload);
          alert('套件创建成功');
        }

        this.closeDialog();
        this.fetchSuites();
      } catch (error) {
        alert('操作失败: ' + (error.message || '未知错误'));
      }
    },
    editSuite(suite) {
      this.editingId = suite.id;
      this.form.name = suite.name;
      this.form.description = suite.description || '';
      this.form.type = suite.type;
      this.scenarioIdsText = suite.scenario_ids?.join(',') || '';
      this.caseIdsText = suite.case_ids?.join(',') || '';
      this.tagsText = suite.tags?.join(',') || '';
      this.showEditDialog = true;
    },
    async deleteSuite(id) {
      if (!confirm('确认删除此套件？')) return;

      try {
        await apiDeleteSuite(id);
        alert('删除成功');
        this.fetchSuites();
      } catch (error) {
        alert('删除失败: ' + (error.message || '未知错误'));
      }
    },
    runSuite(id) {
      this.runningSuiteId = id;
      this.selectedEnvId = null;
      this.showRunDialog = true;
    },
    async executeRun() {
      try {
        this.runResult = await apiRunSuite(this.runningSuiteId, this.selectedEnvId);
        this.showRunDialog = false;
      } catch (error) {
        alert('运行失败: ' + (error.message || '未知错误'));
      }
    },
    closeDialog() {
      this.showCreateDialog = false;
      this.showEditDialog = false;
      this.editingId = null;
      this.form = { name: '', description: '', type: 'mixed' };
      this.scenarioIdsText = '';
      this.caseIdsText = '';
      this.tagsText = '';
    },
    parseIds(text) {
      if (!text) return null;
      return text.split(',').map(s => parseInt(s.trim())).filter(n => !isNaN(n));
    },
    parseTags(text) {
      if (!text) return null;
      return text.split(',').map(s => s.trim()).filter(s => s);
    },
    typeLabel(type) {
      const labels = { scenario: '场景', case: '用例', mixed: '混合' };
      return labels[type] || type;
    },
    typeCount(type) {
      return this.suites.filter(s => s.type === type).length;
    },
    formatDate(dateStr) {
      const d = new Date(dateStr);
      const now = new Date();
      const diff = now - d;
      const days = Math.floor(diff / 86400000);
      if (days === 0) return '今天';
      if (days === 1) return '昨天';
      if (days < 7) return `${days}天前`;
      return d.toLocaleDateString('zh-CN');
    },
  },
};
</script>

<style scoped>
.test-suites {
  padding: 24px;
  max-width: 1800px;
  margin: 0 auto;
}

/* 顶部栏 */
.top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.top-bar h2 {
  font-size: 28px;
  font-weight: 700;
  color: var(--text);
  margin: 0;
}

.btn-create {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s;
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
}

.btn-create:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
}

.btn-create svg {
  width: 18px;
  height: 18px;
}

/* 统计卡片行 */
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 32px;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  transition: all 0.3s;
}

.stat-card:hover {
  border-color: var(--primary);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  transform: translateY(-2px);
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.stat-icon svg {
  width: 24px;
  height: 24px;
  stroke-width: 2;
}

.stat-icon.total {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.stat-icon.scenario {
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
  color: white;
}

.stat-icon.case {
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
  color: white;
}

.stat-icon.mixed {
  background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
  color: white;
}

.stat-info {
  flex: 1;
}

.stat-label {
  font-size: 13px;
  color: var(--text-muted);
  margin-bottom: 4px;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--text);
}

/* 套件卡片网格 - 一行5个 */
.suites-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 20px;
}

@media (max-width: 1800px) {
  .suites-grid {
    grid-template-columns: repeat(4, 1fr);
  }
}

@media (max-width: 1400px) {
  .suites-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 1000px) {
  .suites-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

.suite-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
  transition: all 0.3s;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
}

.suite-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 4px;
  background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
  opacity: 0;
  transition: opacity 0.3s;
}

.suite-card.suite-type-scenario::before {
  background: linear-gradient(90deg, #f093fb 0%, #f5576c 100%);
}

.suite-card.suite-type-case::before {
  background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%);
}

.suite-card.suite-type-mixed::before {
  background: linear-gradient(90deg, #43e97b 0%, #38f9d7 100%);
}

.suite-card:hover {
  border-color: var(--primary);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  transform: translateY(-4px);
}

.suite-card:hover::before {
  opacity: 1;
}

.suite-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}

.suite-title {
  flex: 1;
  min-width: 0;
}

.suite-title h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text);
  margin: 0 0 6px 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.type-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}

.type-badge.type-scenario {
  background: rgba(240, 147, 251, 0.15);
  color: #f5576c;
}

.type-badge.type-case {
  background: rgba(79, 172, 254, 0.15);
  color: #0096ff;
}

.type-badge.type-mixed {
  background: rgba(67, 233, 123, 0.15);
  color: #00b894;
}

.suite-actions {
  display: flex;
  gap: 4px;
  margin-left: 8px;
}

.action-btn {
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 6px;
  background: var(--bg);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  opacity: 0;
}

.suite-card:hover .action-btn {
  opacity: 1;
}

.action-btn svg {
  width: 16px;
  height: 16px;
}

.action-btn.run {
  color: #00b894;
}

.action-btn.run:hover {
  background: rgba(0, 184, 148, 0.1);
}

.action-btn.edit {
  color: #0984e3;
}

.action-btn.edit:hover {
  background: rgba(9, 132, 227, 0.1);
}

.action-btn.delete {
  color: #d63031;
}

.action-btn.delete:hover {
  background: rgba(214, 48, 49, 0.1);
}

.suite-description {
  font-size: 13px;
  color: var(--text-muted);
  margin-bottom: 16px;
  line-height: 1.5;
  min-height: 40px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.suite-stats {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
  padding: 12px;
  background: var(--bg);
  border-radius: 8px;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text);
}

.stat-item svg {
  width: 14px;
  height: 14px;
  color: var(--primary);
  flex-shrink: 0;
}

.stat-item.empty {
  color: var(--text-muted);
  justify-content: center;
}

.suite-footer {
  margin-top: auto;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.create-time {
  font-size: 12px;
  color: var(--text-muted);
}

/* 空状态 */
.empty-state {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: var(--text-muted);
}

.empty-state svg {
  width: 80px;
  height: 80px;
  margin-bottom: 16px;
  opacity: 0.3;
}

.empty-state p {
  font-size: 16px;
  margin-bottom: 20px;
}

.btn-create-empty {
  padding: 10px 24px;
  background: var(--primary);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.3s;
}

.btn-create-empty:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
}

/* 对话框 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(4px);
}

.modal-dialog {
  background: var(--surface);
  border-radius: 16px;
  width: 560px;
  max-height: 80vh;
  overflow: hidden;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.modal-dialog.small {
  width: 400px;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24px;
  border-bottom: 1px solid var(--border);
}

.modal-header h3 {
  font-size: 20px;
  font-weight: 600;
  color: var(--text);
  margin: 0;
}

.close-btn {
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  transition: all 0.2s;
  color: var(--text-muted);
}

.close-btn:hover {
  background: var(--bg);
  color: var(--text);
}

.close-btn svg {
  width: 20px;
  height: 20px;
}

.modal-body {
  padding: 24px;
  max-height: calc(80vh - 140px);
  overflow-y: auto;
}

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

.radio-group {
  display: flex;
  gap: 12px;
}

.radio-option {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.radio-option:hover {
  border-color: var(--primary);
  background: rgba(102, 126, 234, 0.05);
}

.radio-option input {
  margin: 0;
  cursor: pointer;
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

/* 运行结果对话框 */
.result-dialog {
  background: var(--surface);
  border-radius: 16px;
  width: 600px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24px;
  border-bottom: 1px solid var(--border);
}

.result-header h3 {
  font-size: 20px;
  font-weight: 600;
  color: var(--text);
  margin: 0;
}

.result-summary {
  padding: 24px;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.result-stat {
  text-align: center;
  padding: 16px;
  background: var(--bg);
  border-radius: 8px;
}

.result-stat .label {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.result-stat .value {
  font-size: 24px;
  font-weight: 700;
  color: var(--text);
}

.result-stat.pass .value {
  color: #00b894;
}

.result-stat.fail .value {
  color: #d63031;
}

.result-stat.rate .value {
  color: var(--primary);
}

.btn-close-result {
  width: calc(100% - 48px);
  margin: 0 24px 24px;
  padding: 12px;
  background: var(--primary);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-close-result:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
}
</style>
