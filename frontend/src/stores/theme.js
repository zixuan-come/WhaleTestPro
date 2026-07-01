import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useThemeStore = defineStore('theme', () => {
  // 默认亮色(P5),记住用户上次选择
  const theme = ref(localStorage.getItem('wtp_theme') || 'light')

  function apply() {
    document.documentElement.setAttribute('data-theme', theme.value)
  }
  function toggle() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
    localStorage.setItem('wtp_theme', theme.value)
    apply()
  }
  apply()
  return { theme, toggle, apply }
})
