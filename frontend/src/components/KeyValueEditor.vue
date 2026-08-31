<script setup>
const props = defineProps({
  modelValue: {
    type: Array,
    default: () => [],
  },
  nameLabel: {
    type: String,
    default: 'Key',
  },
  valueLabel: {
    type: String,
    default: 'Value',
  },
  namePlaceholder: {
    type: String,
    default: '参数名',
  },
  valuePlaceholder: {
    type: String,
    default: '参数值',
  },
})

const emit = defineEmits(['update:modelValue'])

function updateRow(index, field, value) {
  const rows = props.modelValue.map((row, rowIndex) => (
    rowIndex === index ? { ...row, [field]: value } : row
  ))
  emit('update:modelValue', rows)
}

function addRow() {
  emit('update:modelValue', [
    ...props.modelValue,
    { enabled: true, key: '', value: '' },
  ])
}

function removeRow(index) {
  emit('update:modelValue', props.modelValue.filter((_, rowIndex) => rowIndex !== index))
}
</script>

<template>
  <div class="kv-editor">
    <div class="kv-head" aria-hidden="true">
      <span>{{ nameLabel }}</span>
      <span>{{ valueLabel }}</span>
      <span></span>
    </div>

    <div
      v-for="(row, index) in modelValue"
      :key="index"
      class="kv-row"
      :class="{ disabled: !row.enabled }"
    >
      <input
        type="text"
        :value="row.key"
        :placeholder="namePlaceholder"
        :aria-label="'第 ' + (index + 1) + ' 行' + nameLabel"
        @input="updateRow(index, 'key', $event.target.value)"
      />
      <input
        type="text"
        :value="row.value"
        :placeholder="valuePlaceholder"
        :aria-label="'第 ' + (index + 1) + ' 行' + valueLabel"
        @input="updateRow(index, 'value', $event.target.value)"
      />
      <button
        type="button"
        class="remove-row"
        :aria-label="'删除第 ' + (index + 1) + ' 行'"
        title="删除此行"
        @click="removeRow(index)"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" />
        </svg>
      </button>
    </div>

    <button type="button" class="add-row" @click="addRow">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path d="M12 5v14M5 12h14" />
      </svg>
      添加一行
    </button>
  </div>
</template>

<style scoped>
.kv-editor { background:transparent; }
.kv-head, .kv-row { display:grid; grid-template-columns:minmax(120px,.8fr) minmax(180px,1.2fr) 32px; align-items:center; }
.kv-head { min-height:34px; padding:0 4px; color:var(--text-muted); background:var(--surface-2);
  border-bottom:1px solid var(--border); font-size:11px; font-weight:600; }
.kv-row { gap:8px; padding:8px 4px; border-bottom:1px solid var(--border); transition:opacity .15s,background .15s; }
.kv-row:hover { background:var(--surface-2); }
.kv-row.disabled { opacity:.58; }
.kv-row input[type="text"] { width:100%; min-width:0; height:34px; padding:0 10px; color:var(--text);
  background:var(--surface); border:1px solid var(--border); border-radius:7px; font:12.5px ui-monospace,Consolas,monospace; }
.kv-row input[type="text"]:focus { outline:none; border-color:var(--primary); }
.remove-row { display:inline-flex; align-items:center; justify-content:center; width:26px; height:26px; padding:0;
  color:var(--text-muted); background:transparent; border:none; border-radius:5px; cursor:pointer;
  transition:color .15s,background .15s; }
.remove-row:hover { color:var(--fail-fg); background:var(--fail-bg); }
.remove-row:focus-visible, .add-row:focus-visible { outline:2px solid var(--primary); outline-offset:2px; }
.remove-row svg { width:14px; height:14px; }
.add-row { display:flex; align-items:center; gap:7px; width:100%; padding:9px 4px; color:var(--primary);
  background:transparent; border:none; cursor:pointer; font:600 12px inherit; transition:color .15s,background .15s; }
.add-row:hover { background:var(--surface-2); }
.add-row svg { width:15px; height:15px; }

@media (max-width:620px) {
  .kv-head { grid-template-columns:1fr 1fr 28px; }
  .kv-row { grid-template-columns:1fr 1fr 28px; gap:6px; }
  .kv-row input[type="text"] { min-width:0; }
}
</style>