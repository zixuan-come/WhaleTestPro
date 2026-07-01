<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { login as apiLogin } from '../api/auth'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'
import { computed } from 'vue'

const router = useRouter()
const auth = useAuthStore()
const themeStore = useThemeStore()
const isDark = computed(() => themeStore.theme === 'dark')

const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function onSubmit() {
  error.value = ''
  if (!username.value || !password.value) {
    error.value = '请输入账号和密码'
    return
  }
  loading.value = true
  try {
    const res = await apiLogin(username.value, password.value)
    auth.setAuth(res.access_token, username.value)
    router.push({ name: 'interfaces' })
  } catch (e) {
    error.value = e.message || '登录失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login">
    <!-- 主题切换 -->
    <button class="theme-btn" @click="themeStore.toggle()" :title="isDark ? '切到亮色' : '切到暗色'">
      <svg v-if="isDark" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M19 5l-1.5 1.5M6.5 17.5L5 19" />
      </svg>
      <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z" />
      </svg>
    </button>

    <div class="card">
      <!-- 品牌侧 -->
      <aside class="brand">
        <div class="brand-top">
          <div class="mark">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
              <path d="M3 12c3-6 15-6 18 0-3 6-15 6-18 0z" />
              <circle cx="12" cy="12" r="2.2" fill="currentColor" stroke="none" />
            </svg>
          </div>
          <h2>WhaleTestPro</h2>
          <p>一站式接口测试 · 压测 · 流量回放平台</p>
          <ul>
            <li><span class="tick"></span>接口用例串联 · 数据驱动</li>
            <li><span class="tick"></span>分布式压测 · 实时监控</li>
            <li><span class="tick"></span>流量录制回放 · 智能 diff</li>
          </ul>
        </div>
        <!-- 鲸鱼波浪动效 -->
        <svg class="waves" viewBox="0 0 400 80" preserveAspectRatio="none">
          <path class="wave w1" d="M0,40 C100,10 300,70 400,40 L400,80 L0,80 Z" />
          <path class="wave w2" d="M0,50 C120,20 280,80 400,45 L400,80 L0,80 Z" />
        </svg>
      </aside>

      <!-- 表单侧 -->
      <form class="form" @submit.prevent="onSubmit">
        <h1>欢迎回来</h1>
        <p class="sub">登录以继续你的测试工作台</p>

        <label>账号</label>
        <div class="field">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="8" r="4" /><path d="M4 21v-1a6 6 0 0112 0v1" />
          </svg>
          <input v-model="username" type="text" placeholder="请输入账号" autocomplete="username" />
        </div>

        <label>密码</label>
        <div class="field">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="4" y="11" width="16" height="9" rx="2" /><path d="M8 11V7a4 4 0 018 0v4" />
          </svg>
          <input v-model="password" type="password" placeholder="请输入密码" autocomplete="current-password" />
        </div>

        <transition name="fade">
          <p v-if="error" class="err">{{ error }}</p>
        </transition>

        <button class="submit" type="submit" :disabled="loading">
          {{ loading ? '登录中…' : '登 录' }}
        </button>

        <p class="foot">测试平台演示环境 · WhaleTestPro</p>
      </form>
    </div>
  </div>
</template>

<style scoped>
.login { height:100vh; display:grid; place-items:center; padding:24px; background:var(--bg); position:relative; }

.theme-btn { position:absolute; top:22px; right:24px; z-index:3; width:40px; height:40px; border-radius:10px;
  display:grid; place-items:center; cursor:pointer; color:var(--text);
  background:var(--surface); border:1px solid var(--border); transition:border-color .15s; }
.theme-btn:hover { border-color:var(--primary); }
.theme-btn svg { width:18px; height:18px; }

/* 卡片:实底 + 细边 + 收敛阴影,不做玻璃模糊 */
.card { display:grid; grid-template-columns:320px 380px; border-radius:16px;
  overflow:hidden; border:1px solid var(--border); background:var(--surface);
  box-shadow:var(--shadow-lg); animation:rise .4s ease; }
@keyframes rise { from { opacity:0; transform:translateY(10px); } to { opacity:1; transform:translateY(0); } }

/* 品牌侧:实色主蓝,底部一道静态海浪点鲸鱼+大海主题 */
.brand { position:relative; padding:42px 34px; color:#fff; overflow:hidden; background:var(--primary); }
.brand-top { position:relative; z-index:1; }
.mark { width:50px; height:50px; border-radius:14px; display:grid; place-items:center;
  background:rgba(255,255,255,.16); margin-bottom:22px; }
.mark svg { width:28px; height:28px; }
.brand h2 { font-size:23px; font-weight:800; margin-bottom:8px; letter-spacing:.3px; }
.brand > .brand-top > p { font-size:13px; opacity:.9; margin-bottom:28px; line-height:1.6; }
.brand ul { list-style:none; display:flex; flex-direction:column; gap:14px; }
.brand li { font-size:12.5px; opacity:.95; display:flex; align-items:center; gap:10px; }
.tick { width:18px; height:18px; border-radius:50%; flex-shrink:0; display:inline-grid; place-items:center;
  background:rgba(255,255,255,.18); position:relative; }
.tick::after { content:""; width:5px; height:9px; border:solid #fff; border-width:0 2px 2px 0;
  transform:rotate(45deg) translate(-1px,-1px); }
.waves { position:absolute; left:0; right:0; bottom:0; width:100%; height:62px; }
.wave { fill:rgba(255,255,255,.10); }
.wave.w2 { fill:rgba(255,255,255,.07); }

/* 表单侧 */
.form { padding:46px 38px; display:flex; flex-direction:column; background:var(--surface); }
.form h1 { font-size:22px; font-weight:800; }
.form .sub { font-size:13px; color:var(--text-muted); margin:6px 0 28px; }
.form label { font-size:12.5px; font-weight:650; margin-bottom:7px; }
.field { position:relative; margin-bottom:18px; }
.field svg { position:absolute; left:13px; top:50%; transform:translateY(-50%);
  width:17px; height:17px; color:var(--text-muted); pointer-events:none; transition:color .18s; }
.field input { width:100%; background:var(--surface-2); border:1px solid var(--border); border-radius:10px;
  padding:12px 13px 12px 40px; font-size:13.5px; color:var(--text); outline:none; transition:border-color .18s; }
.field input:focus { border-color:var(--primary); }
.field input:focus + svg, .field:focus-within svg { color:var(--primary); }
.err { color:var(--fail-fg); font-size:12.5px; margin:-6px 0 14px; }
.fade-enter-active,.fade-leave-active { transition:opacity .2s; }
.fade-enter-from,.fade-leave-to { opacity:0; }

.submit { justify-content:center; padding:12px; font-size:14.5px; font-weight:700; color:#fff;
  border:none; border-radius:10px; cursor:pointer; margin-top:6px;
  background:var(--primary); transition:filter .15s; }
.submit:hover { filter:brightness(.95); }
.submit:disabled { opacity:.6; cursor:not-allowed; }
.foot { text-align:center; font-size:11px; color:var(--text-muted); margin-top:20px; }

/* ===== 响应式:窄屏隐藏品牌侧,卡片收成单栏表单 ===== */
@media (max-width:720px) {
  .card { grid-template-columns:1fr; width:min(380px,100%); }
  .brand { display:none; }
  .form { padding:38px 26px; }
}
</style>
