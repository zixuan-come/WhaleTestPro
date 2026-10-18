<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useAuthStore } from '../stores/auth'
import { getProjectNotifications, saveProjectNotifications, testProjectNotifications } from '../api/project'
import { showMessage } from '../composables/feedback'
import Modal from './Modal.vue'

const props = defineProps({ project: { type: Object, required: true } })
const emit = defineEmits(['close'])
const auth = useAuthStore()
const loading = ref(false), saving = ref(false), testing = ref(false), error = ref(''), testResult = ref('')
const settings = ref(null)
const form = reactive({ enabled: false, webhook: '', secret: '', clearWebhook: false, clearSecret: false })
let version = 0
const contextKey = computed(() => `${props.project.id}:${auth.username}:${auth.token}:${auth.currentTeamRole}`)
const busy = computed(() => saving.value || testing.value)
const canManage = computed(() => !!settings.value?.can_manage && ['owner', 'admin'].includes(auth.currentTeamRole))
const dirty = computed(() => form.enabled !== !!settings.value?.enabled || !!form.webhook.trim() || !!form.secret.trim() || form.clearWebhook || form.clearSecret)

function resetForm() { Object.assign(form, { enabled: !!settings.value?.enabled, webhook: '', secret: '', clearWebhook: false, clearSecret: false }) }
async function load() {
  const current = ++version, context = contextKey.value
  loading.value = true; error.value = ''; settings.value = null; testResult.value = ''; resetForm()
  try { const result = await getProjectNotifications(props.project.id); if (current === version && context === contextKey.value) { settings.value = result; resetForm() } }
  catch (e) { if (current === version && context === contextKey.value) error.value = e.message || '通知配置加载失败' }
  finally { if (current === version) loading.value = false }
}
async function save() {
  if (busy.value || loading.value || !canManage.value) return
  error.value = ''; testResult.value = ''
  if (form.enabled && !(form.webhook.trim() || (settings.value.configured && !form.clearWebhook))) { error.value = '启用前请先填写 Webhook 地址'; return }
  const current = version, context = contextKey.value
  const payload = { enabled: form.enabled, ...(form.webhook.trim() ? { webhook_url: form.webhook.trim() } : {}), ...(form.secret.trim() ? { signing_secret: form.secret.trim() } : {}), clear_webhook: form.clearWebhook, clear_signing_secret: form.clearSecret }
  saving.value = true
  try { const result = await saveProjectNotifications(props.project.id, payload); if (current !== version || context !== contextKey.value) return; settings.value = result; resetForm(); showMessage('通知配置已保存') }
  catch (e) { if (current === version && context === contextKey.value) error.value = e.message || '保存失败，请重试' }
  finally { if (current === version) saving.value = false }
}
async function sendTest() {
  if (busy.value || loading.value || !canManage.value || !settings.value?.configured || dirty.value) return
  const current = version, context = contextKey.value
  testing.value = true; error.value = ''; testResult.value = ''
  try { await testProjectNotifications(props.project.id); if (current === version && context === contextKey.value) testResult.value = '测试通知已发送，请到飞书群查看。' }
  catch (e) { if (current === version && context === contextKey.value) error.value = e.message || '测试通知发送失败' }
  finally { if (current === version) testing.value = false }
}
function close() { if (!busy.value) emit('close') }
watch(contextKey, () => { saving.value = false; testing.value = false; load() }, { immediate: true, flush: 'sync' })
onBeforeUnmount(() => { version++; resetForm(); settings.value = null })
</script>

<template>
  <Modal title="项目通知设置" :max-width="560" :busy="busy" hide-scrollbar @close="close">
    <p class="notification-project">{{ project.name }}</p>
    <div v-if="loading" class="notification-state" role="status">正在加载通知配置…</div>
    <template v-else-if="settings">
      <div class="notification-heading"><strong>飞书通知</strong><span class="badge" :class="settings.configured && settings.enabled ? 'b-pass' : 'b-skip'">{{ !settings.configured ? '未配置' : settings.enabled ? '已启用' : '已停用' }}</span></div>
      <p v-if="!canManage" class="notification-note">只有项目所属团队的所有者、管理员可以修改通知设置。</p>
      <fieldset :disabled="busy || !canManage" class="notification-fields">
        <label class="notification-checkbox"><input type="checkbox" v-model="form.enabled" />启用本项目的飞书通知</label>
        <label class="notification-field">Webhook 地址<input type="password" v-model="form.webhook" autocomplete="new-password" spellcheck="false" maxlength="512" :disabled="form.clearWebhook || busy || !canManage" :placeholder="settings.configured ? '已保存，留空保留原地址' : '粘贴飞书自定义机器人的 Webhook 地址'" /></label>
        <p class="notification-note">在飞书群设置中添加自定义机器人，复制 Webhook 地址到这里。地址保存后不再回显。</p>
        <label v-if="settings.configured" class="notification-checkbox clear"><input type="checkbox" v-model="form.clearWebhook" @change="form.webhook = ''; form.secret = ''; form.enabled = form.clearWebhook ? false : settings.enabled" />清除已保存的 Webhook 地址</label>
        <details class="notification-advanced"><summary>机器人安全设置（可选）</summary>
          <p class="notification-note">如启用关键词校验，请在飞书机器人中允许关键词 <strong>WhaleTestPro</strong>。</p>
          <label class="notification-field">签名密钥<input type="password" v-model="form.secret" autocomplete="new-password" spellcheck="false" maxlength="512" :disabled="form.clearSecret || form.clearWebhook || busy || !canManage" :placeholder="settings.signing_configured ? '已保存，留空保留原密钥' : '仅在机器人启用签名校验时填写'" /></label>
          <label v-if="settings.signing_configured" class="notification-checkbox clear"><input type="checkbox" v-model="form.clearSecret" @change="form.secret = ''" />清除已保存的签名密钥</label>
          <p class="notification-note">如设置 IP 白名单，请允许部署服务器的出口 IP。</p>
        </details>
      </fieldset>
      <p v-if="dirty" class="notification-note pending">配置有修改，请先保存，再发送测试通知。</p>
      <p v-if="testResult" class="notification-success" role="status">{{ testResult }}</p>
    </template>
    <p v-if="error" class="notification-error" role="alert">{{ error }}<button v-if="!settings" class="btn btn-ghost" @click="load">重试</button></p>
    <template #foot><div class="notification-footer"><button type="button" class="btn btn-ghost" :disabled="busy" @click="close">关闭</button><button type="button" class="btn btn-ghost" :disabled="busy || loading || !canManage || !settings?.configured || dirty" @click="sendTest">{{ testing ? '发送中…' : '发送测试通知' }}</button><button type="button" class="btn btn-primary" :disabled="busy || loading || !canManage || !dirty" @click="save">{{ saving ? '保存中…' : '保存' }}</button></div></template>
  </Modal>
</template>

<style scoped>
.notification-project { margin:0 0 18px;font-size:13px;color:var(--text-muted);overflow-wrap:anywhere; }.notification-heading { display:flex;align-items:center;gap:12px;margin-bottom:18px; }.notification-heading strong { font-size:14px; }
.notification-fields { border:0;padding:0;margin:0;min-width:0; }.notification-checkbox { display:flex;align-items:center;gap:8px;font-size:12px;line-height:1.7;cursor:pointer; }.notification-checkbox input { accent-color:var(--primary);width:14px;height:14px;flex:none; }.notification-checkbox.clear { color:var(--text-muted);margin-top:10px; }
.notification-field { display:block;margin-top:18px;font-size:12px;font-weight:600; }.notification-field input { display:block;width:100%;height:36px;margin-top:8px;padding:0 10px;border:1px solid var(--border);border-radius:6px;background:var(--surface-2);color:var(--text);font:inherit;font-weight:400; }.notification-field input:focus { outline:2px solid var(--ring);border-color:var(--primary); }
.notification-note { margin:9px 0 0;font-size:11px;color:var(--text-muted);line-height:1.8; }.notification-advanced { margin-top:18px;border-top:1px solid var(--border);padding-top:14px; }.notification-advanced summary { font-size:12px;cursor:pointer;color:var(--text-muted); }.notification-advanced summary:focus-visible { outline:2px solid var(--primary); }.pending { color:var(--warn-fg); }
.notification-error,.notification-success { margin:14px 0 0;padding:10px 12px;border-radius:6px;font-size:12px;line-height:1.7;overflow-wrap:anywhere; }.notification-error { background:var(--fail-bg);color:var(--fail-fg); }.notification-error button { margin-left:10px;font-size:12px; }.notification-success { background:var(--pass-bg);color:var(--pass-fg); }.notification-state { padding:30px 0;text-align:center;font-size:12px;color:var(--text-muted); }button:disabled { opacity:.5;cursor:default; }
.notification-footer { display:flex;justify-content:flex-end;flex-wrap:wrap;gap:8px;width:100%; }
</style>
