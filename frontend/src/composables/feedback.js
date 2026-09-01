import { ref } from 'vue'

const notice = ref(null)
const confirmState = ref(null)
let noticeTimer = null
let confirmResolver = null

export function showMessage(message, type = 'success', duration = 3200) {
  notice.value = { message, type }
  clearTimeout(noticeTimer)
  noticeTimer = setTimeout(() => { notice.value = null }, duration)
}

export function confirmAction(message, title = '请确认操作') {
  confirmState.value = { title, message }
  return new Promise((resolve) => { confirmResolver = resolve })
}

export function resolveConfirm(result) {
  if (confirmResolver) confirmResolver(result)
  confirmResolver = null
  confirmState.value = null
}

export function useFeedback() {
  return { notice, confirmState, showMessage, confirmAction, resolveConfirm }
}