<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useThemeStore } from '../stores/theme'
import { useAuthStore } from '../stores/auth'

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
      { to: '/interfaces', text: '接口用例', icon: 'M4 6h16M4 12h16M4 18h10' },
      { to: '/reports', text: '测试报告', icon: 'M9 17V9m4 8V5m4 12v-6 M4 20h16' },
      { to: '/traffic', text: '流量回放', icon: 'M5 3l14 9-14 9V3z' },
    ],
  },
  {
    label: '运维',
    items: [
      { to: '/perf', text: '压测监控', icon: 'M3 12h4l3 8 4-16 3 8h4' },
      { to: '/environments', text: '环境管理', icon: 'M12 8a4 4 0 100-8 4 4 0 000 8z M4 21v-1a6 6 0 0112 0v1' },
    ],
  },
]

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
          <span class="search">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" />
            </svg>
            搜索…
          </span>
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
  cursor:pointer; transition:background .15s,color .15s; }
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
.search { display:flex; align-items:center; gap:8px; background:var(--surface-2);
  border:1px solid var(--border); border-radius:8px; padding:8px 13px; font-size:12.5px;
  color:var(--text-muted); min-width:180px; cursor:text; transition:border-color .18s; }
.search svg { width:15px; height:15px; }
.search:hover { border-color:var(--primary); }
.toggle { display:inline-flex; align-items:center; justify-content:center; gap:8px; height:32px;
  background:var(--surface-2); border:1px solid var(--border); color:var(--text);
  font-size:14px; font-weight:400; line-height:1.5715; padding:0 15px; border-radius:4px;
  cursor:pointer; white-space:nowrap; transition:background .25s,border-color .18s; }
.toggle:hover { border-color:var(--primary); }
.toggle svg { width:14px; height:14px; }
.content { padding:26px; overflow:auto; flex:1; }

/* ===== 响应式:1920 为默认基准,以下是往小屏收 ===== */
/* 笔记本 ≤1366:侧栏略收窄,内边距减一点 */
@media (max-width:1366px) {
  .app { grid-template-columns:196px 1fr; }
  .content { padding:22px; }
}
/* 平板 ≤900:侧栏收成「图标条」,只留图标 */
@media (max-width:900px) {
  .app { grid-template-columns:62px 1fr; }
  .side { padding:16px 8px; align-items:center; }
  .logo { justify-content:center; padding:0; }
  .logo .txt, .nav .label, .nav-label, .who { display:none; }
  .nav { justify-content:center; padding:11px; gap:0; }
  .nav.active::before { display:none; }
  .side-foot { justify-content:center; padding:8px; }
  .topbar { padding:13px 18px; }
  .search { min-width:0; }
}
/* 手机 ≤600:侧栏从「左侧竖条」变「顶部横条」,整体单列堆叠 */
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
  .search { display:none; }
}
</style>
