<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useThemeStore } from '../stores/theme'
import { useAuthStore } from '../stores/auth'
import { listProjects, createProject } from '../api/project'
import Modal from '../components/Modal.vue'

const route = useRoute()
const router = useRouter()
const themeStore = useThemeStore()
const auth = useAuthStore()

const isDark = computed(() => themeStore.theme === 'dark')
const title = computed(() => route.meta.title || 'WhaleTestPro')
const crumb = computed(() => route.meta.crumb || '')

// 导航分组配置:加模块只改这里
const navGroups = [
  {
    label: '测试',
    items: [
      { to: '/interfaces', text: '接口管理', icon: 'M4 6h16M4 12h16M4 18h10' },
      { to: '/cases', text: '测试用例', icon: 'M9 11l3 3L22 4 M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11' },
      { to: '/orchestration', text: '场景编排', icon: 'M4 6h4v4H4zM16 6h4v4h-4zM10 14h4v4h-4zM8 8h8M12 10v4' },
      { to: '/reports', text: '测试报告', icon: 'M9 17V9m4 8V5m4 12v-6 M4 20h16' },
      { to: '/regression', text: '回归执行', icon: 'M21 12a9 9 0 11-3-6.7M21 3v5h-5' },
      { to: '/traffic', text: '流量回放', icon: 'M5 3l14 9-14 9V3z' },
    ],
  },
  {
    label: '运维',
    items: [
      { to: '/perf', text: '压测监控', icon: 'M3 12h4l3 8 4-16 3 8h4' },
      { to: '/mocks', text: 'Mock 挡板', icon: 'M4 7h16M4 12h16M4 17h10 M7 4v16' },
      { to: '/schedules', text: '定时调度', icon: 'M12 7v5l3 2 M12 21a9 9 0 100-18 9 9 0 000 18z' },
      { to: '/environments', text: '环境管理', icon: 'M12 8a4 4 0 100-8 4 4 0 000 8z M4 21v-1a6 6 0 0112 0v1' },
    ],
  },
  {
    label: '系统',
    items: [
      { to: '/projects', text: '项目管理', icon: 'M3 7l9-4 9 4-9 4-9-4z M3 12l9 4 9-4 M3 17l9 4 9-4' },
    ],
  },
]

// ==================== 项目切换器 ====================
const projectDropdownOpen = ref(false)
const projects = ref([])
const projectsLoading = ref(false)

const showCreateProjectModal = ref(false)
const savingProject = ref(false)
const projectFormErr = ref('')
const projectForm = ref({ name: '', description: '' })

async function loadProjects() {
  projectsLoading.value = true
  try {
    projects.value = await listProjects()
  } catch (e) {
    // 静默失败,下拉会显示"加载失败"提示
    projects.value = []
  } finally {
    projectsLoading.value = false
  }
}

async function toggleProjectDropdown() {
  projectDropdownOpen.value = !projectDropdownOpen.value
  if (projectDropdownOpen.value) await loadProjects()
}

function switchProject(p) {
  auth.setProject(p.id, p.name)
  projectDropdownOpen.value = false
  // 切项目后刷新当前页,让列表用新的 pid 重拉
  router.go(0)
}

function openCreateProject() {
  projectForm.value = { name: '', description: '' }
  projectFormErr.value = ''
  showCreateProjectModal.value = true
  projectDropdownOpen.value = false
}

function closeCreateProject() {
  if (savingProject.value) return
  showCreateProjectModal.value = false
}

async function saveProject() {
  projectFormErr.value = ''
  if (!projectForm.value.name.trim()) { projectFormErr.value = '请填写项目名称'; return }
  savingProject.value = true
  try {
    const created = await createProject({
      name: projectForm.value.name.trim(),
      description: projectForm.value.description.trim() || null,
    })
    showCreateProjectModal.value = false
    auth.setProject(created.id, created.name)
    router.go(0)
  } catch (e) {
    projectFormErr.value = e.message || '创建失败'
  } finally {
    savingProject.value = false
  }
}

// 点外部关闭下拉
function onOutsideClick(e) {
  if (!e.target.closest('.project-switcher')) projectDropdownOpen.value = false
}
onMounted(() => document.addEventListener('click', onOutsideClick))
onBeforeUnmount(() => document.removeEventListener('click', onOutsideClick))

function onLogout() {
  auth.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <div class="app">
    <aside class="side">
      <div class="logo">
        <span class="mark">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
            <path d="M3 12c3-6 15-6 18 0-3 6-15 6-18 0z" />
            <circle cx="12" cy="12" r="2.2" fill="currentColor" stroke="none" />
          </svg>
        </span>
        <span class="txt">WhaleTestPro</span>
      </div>

      <template v-for="group in navGroups" :key="group.label">
        <div class="nav-label">{{ group.label }}</div>
        <router-link
          v-for="item in group.items"
          :key="item.to"
          :to="item.to"
          class="nav"
          active-class="active"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path :d="item.icon" />
          </svg>
          <span class="label">{{ item.text }}</span>
        </router-link>
      </template>

      <div class="side-foot">
        <span class="avatar"></span>
        <div class="who">
          <div class="name">{{ auth.username || '测试团队' }}</div>
          <div class="role">已登录</div>
        </div>
        <button class="logout" title="退出登录" @click="onLogout">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" />
          </svg>
        </button>
      </div>
    </aside>

    <div class="main">
      <header class="topbar">
        <div>
          <h1>{{ title }}</h1>
          <div class="crumb">工作台 / {{ crumb }}</div>
        </div>
        <div class="actions">
          <!-- 项目切换器 -->
          <div class="project-switcher" :class="{ open: projectDropdownOpen }">
            <button class="switcher-btn" @click.stop="toggleProjectDropdown" :title="auth.currentProjectName || '未选择项目'">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M3 7l9-4 9 4-9 4-9-4z M3 12l9 4 9-4 M3 17l9 4 9-4" />
              </svg>
              <span class="pname">{{ auth.currentProjectName || '选择项目' }}</span>
              <svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M6 9l6 6 6-6" />
              </svg>
            </button>
            <div v-if="projectDropdownOpen" class="dropdown" @click.stop>
              <div class="dd-head">切换项目</div>
              <div v-if="projectsLoading" class="dd-state">加载中…</div>
              <div v-else-if="!projects.length" class="dd-state">还没有项目,先建一个吧</div>
              <div v-else class="dd-list">
                <button
                  v-for="p in projects"
                  :key="p.id"
                  class="dd-item"
                  :class="{ active: p.id === auth.currentProjectId }"
                  @click="switchProject(p)"
                >
                  <span class="dd-name">{{ p.name }}</span>
                  <svg v-if="p.id === auth.currentProjectId" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <path d="M5 13l4 4L19 7" />
                  </svg>
                </button>
              </div>
              <div class="dd-foot">
                <button class="dd-action" @click="openCreateProject">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14" /></svg>
                  新建项目
                </button>
                <router-link to="/projects" class="dd-action" @click="projectDropdownOpen = false">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6h16M4 12h16M4 18h10" /></svg>
                  管理项目
                </router-link>
              </div>
            </div>
          </div>

          <button class="toggle" @click="themeStore.toggle()">
            <svg v-if="isDark" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="4" />
              <path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M19 5l-1.5 1.5M6.5 17.5L5 19" />
            </svg>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z" />
            </svg>
            {{ isDark ? '亮色' : '暗色' }}
          </button>
        </div>
      </header>

      <main class="content">
        <router-view />
      </main>
    </div>

    <!-- 快捷新建项目弹窗 -->
    <Modal v-if="showCreateProjectModal" title="新建项目" :busy="savingProject" @close="closeCreateProject">
      <div class="mfield">
        <label>项目名称</label>
        <input v-model="projectForm.name" placeholder="如:电商压测项目" />
      </div>
      <div class="mfield">
        <label>简介 <span class="opt">(可选)</span></label>
        <textarea v-model="projectForm.description" rows="3" placeholder="这个项目是干嘛的"></textarea>
      </div>
      <div v-if="projectFormErr" class="mform-err">{{ projectFormErr }}</div>
      <template #foot>
        <button class="btn btn-ghost" @click="closeCreateProject" :disabled="savingProject">取消</button>
        <button class="btn btn-primary" @click="saveProject" :disabled="savingProject">
          {{ savingProject ? '创建中…' : '创建并切换' }}
        </button>
      </template>
    </Modal>
  </div>
</template>

<style scoped>
.app { display:grid; grid-template-columns:212px 1fr; height:100vh; }

.side { background:var(--surface); border-right:1px solid var(--border); padding:20px 14px;
  display:flex; flex-direction:column; transition:background .3s,border-color .3s; }
.logo { display:flex; align-items:center; gap:9px; font-size:15.5px; font-weight:750;
  margin-bottom:26px; padding:2px 6px; letter-spacing:.2px; }
.logo .mark { width:30px; height:30px; border-radius:9px; display:grid; place-items:center;
  background:linear-gradient(135deg,var(--primary),var(--primary-2)); color:#fff; }
.logo .mark svg { width:18px; height:18px; }
.logo .txt { color:var(--text); }
.nav-label { font-size:11px; font-weight:600; color:var(--text-muted); text-transform:uppercase;
  letter-spacing:.6px; padding:0 8px; margin:6px 0 8px; opacity:.7; }
.nav { position:relative; display:flex; align-items:center; gap:10px; font-size:13px; font-weight:550;
  padding:9px 12px; border-radius:8px; color:var(--text-muted); margin-bottom:3px;
  cursor:pointer; transition:background .15s,color .15s; text-decoration:none; }
.nav svg { width:16px; height:16px; flex-shrink:0; }
.nav:hover { background:var(--surface-2); color:var(--text); }
.nav.active { background:var(--surface-2); color:var(--primary); font-weight:650; }
.nav.active::before { content:""; position:absolute; left:-14px; top:50%; transform:translateY(-50%);
  width:3px; height:18px; border-radius:0 3px 3px 0; background:var(--primary); }
.side-foot { margin-top:auto; display:flex; align-items:center; gap:9px; padding:10px 12px;
  border-radius:10px; background:var(--surface-2); font-size:12px; }
.avatar { width:28px; height:28px; border-radius:50%; flex-shrink:0; background:var(--primary); }
.who { flex:1; min-width:0; }
.who .name { font-weight:650; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.who .role { font-size:11px; color:var(--text-muted); }
.logout { background:none; border:none; color:var(--text-muted); cursor:pointer; padding:4px;
  border-radius:7px; display:grid; place-items:center; transition:color .15s,background .15s; }
.logout svg { width:16px; height:16px; }
.logout:hover { color:var(--fail-fg); background:var(--fail-bg); }

.main { display:flex; flex-direction:column; overflow:hidden; }
.topbar { position:sticky; top:0; z-index:5; display:flex; align-items:center; justify-content:space-between;
  padding:15px 26px; background:var(--surface); border-bottom:1px solid var(--border);
  transition:background .3s,border-color .3s; }
.topbar h1 { font-size:18px; font-weight:750; letter-spacing:.2px; }
.crumb { font-size:12px; color:var(--text-muted); margin-top:2px; }
.actions { display:flex; align-items:center; gap:11px; }

/* ===== 项目切换器 ===== */
.project-switcher { position:relative; }
.switcher-btn { display:inline-flex; align-items:center; gap:8px; height:34px; padding:0 12px;
  background:var(--surface-2); border:1px solid var(--border); color:var(--text);
  border-radius:8px; cursor:pointer; font-size:13px; font-weight:550; min-width:170px;
  transition:border-color .18s,background .18s; }
.switcher-btn:hover, .project-switcher.open .switcher-btn { border-color:var(--primary); }
.switcher-btn svg { width:15px; height:15px; color:var(--text-muted); flex-shrink:0; }
.switcher-btn .pname { flex:1; text-align:left; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.switcher-btn .chev { transition:transform .2s; }
.project-switcher.open .switcher-btn .chev { transform:rotate(180deg); color:var(--primary); }

.dropdown { position:absolute; top:calc(100% + 6px); right:0; min-width:260px; max-width:320px;
  background:var(--surface); border:1px solid var(--border); border-radius:10px;
  box-shadow:var(--shadow-lg); overflow:hidden; z-index:10; animation:pop .14s ease; }
@keyframes pop { from { opacity:0; transform:translateY(-4px); } to { opacity:1; transform:translateY(0); } }

.dd-head { font-size:11px; font-weight:600; color:var(--text-muted); text-transform:uppercase;
  letter-spacing:.5px; padding:12px 14px 8px; }
.dd-state { padding:20px 14px; text-align:center; font-size:12.5px; color:var(--text-muted); }
.dd-list { max-height:280px; overflow-y:auto; }
.dd-item { display:flex; align-items:center; justify-content:space-between; gap:10px;
  width:100%; padding:9px 14px; background:none; border:none; cursor:pointer;
  font-size:13px; color:var(--text); text-align:left; transition:background .12s; }
.dd-item:hover { background:var(--surface-2); }
.dd-item.active { color:var(--primary); font-weight:650; background:var(--surface-2); }
.dd-item svg { width:15px; height:15px; flex-shrink:0; }
.dd-name { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }

.dd-foot { border-top:1px solid var(--border); display:flex; }
.dd-action { flex:1; display:inline-flex; align-items:center; justify-content:center; gap:6px;
  padding:10px; background:none; border:none; color:var(--primary); font-size:12.5px; font-weight:600;
  cursor:pointer; text-decoration:none; transition:background .12s; }
.dd-action + .dd-action { border-left:1px solid var(--border); }
.dd-action:hover { background:var(--surface-2); }
.dd-action svg { width:14px; height:14px; }

.toggle { display:inline-flex; align-items:center; justify-content:center; gap:8px; height:34px;
  background:var(--surface-2); border:1px solid var(--border); color:var(--text);
  font-size:13px; padding:0 13px; border-radius:8px;
  cursor:pointer; white-space:nowrap; transition:border-color .18s; }
.toggle:hover { border-color:var(--primary); }
.toggle svg { width:14px; height:14px; }

.content { padding:26px; overflow:auto; flex:1; }

/* Modal 内表单 */
.mfield { margin-bottom:18px; }
.mfield label { display:block; font-size:12.5px; font-weight:600; margin-bottom:8px; color:var(--text); }
.mfield label .opt { color:var(--text-muted); font-weight:400; }
.mfield input, .mfield textarea { width:100%; padding:0 12px; font-size:13px; color:var(--text);
  background:var(--surface-2); border:1px solid var(--border); border-radius:8px; font-family:inherit;
  transition:border-color .15s; }
.mfield input { height:38px; }
.mfield textarea { padding:10px 12px; resize:vertical; }
.mfield input:focus, .mfield textarea:focus { outline:none; border-color:var(--primary); }
.mform-err { color:var(--fail-fg); font-size:12.5px; background:var(--fail-bg); padding:9px 12px; border-radius:8px; }

/* ===== 响应式:1920 为默认基准,以下是往小屏收 ===== */
@media (max-width:1366px) {
  .app { grid-template-columns:196px 1fr; }
  .content { padding:22px; }
}
@media (max-width:900px) {
  .app { grid-template-columns:62px 1fr; }
  .side { padding:16px 8px; align-items:center; }
  .logo { justify-content:center; padding:0; }
  .logo .txt, .nav .label, .nav-label, .who { display:none; }
  .nav { justify-content:center; padding:11px; gap:0; }
  .nav.active::before { display:none; }
  .side-foot { justify-content:center; padding:8px; }
  .topbar { padding:13px 18px; }
  .switcher-btn { min-width:0; padding:0 10px; }
  .switcher-btn .pname { max-width:100px; }
}
@media (max-width:600px) {
  .app { grid-template-columns:1fr; grid-template-rows:auto 1fr; }
  .side { flex-direction:row; align-items:center; gap:4px; padding:8px 10px;
    overflow-x:auto; border-right:none; border-bottom:1px solid var(--border); }
  .logo { margin-bottom:0; flex-shrink:0; }
  .nav { margin-bottom:0; white-space:nowrap; flex-shrink:0; }
  .side-foot { margin-top:0; margin-left:auto; flex-shrink:0; }
  .content { padding:16px; }
  .topbar { padding:12px 16px; }
  .topbar h1 { font-size:16px; }
  .switcher-btn .pname { max-width:80px; }
}
</style>
