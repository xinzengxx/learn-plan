<script setup lang="ts">
import { computed } from 'vue'
import type { DisplayValue } from '../types'

const props = defineProps<{
  value?: DisplayValue
  fallback?: string
}>()

const MAX_CELL_CHARS = 160

const tableRows = computed(() => {
  if (!props.value || !('rows' in props.value) || !Array.isArray(props.value.rows)) return []
  return props.value.rows.map((row) => Array.isArray(row) ? row : [row])
})

const tableColumns = computed(() => {
  if (!props.value || !('columns' in props.value) || !Array.isArray(props.value.columns)) return []
  return props.value.columns.map(String)
})

const seriesRows = computed(() => {
  if (!props.value || props.value.kind !== 'series' || !Array.isArray(props.value.values)) return []
  return props.value.values.map((value, index) => [index, value])
})

const fallbackText = computed(() => props.fallback || props.value?.repr || ('value' in (props.value || {}) ? stringify((props.value as { value?: unknown }).value) : ''))
const shapeText = computed(() => props.value && 'shape' in props.value && Array.isArray(props.value.shape) ? props.value.shape.join(' × ') : '')

function stringify(value: unknown): string {
  if (value === undefined || value === null) return ''
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function formatCell(value: unknown): string {
  const text = stringify(value)
  return text.length > MAX_CELL_CHARS ? `${text.slice(0, MAX_CELL_CHARS)}…` : text
}
</script>

<template>
  <div v-if="props.value" class="display-value-view" :data-kind="props.value.kind">
    <div v-if="props.value.kind === 'dataframe' || props.value.kind === 'sql_result'" class="display-table-wrap">
      <table class="display-table">
        <thead>
          <tr>
            <th v-for="column in tableColumns" :key="column">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, rowIndex) in tableRows" :key="rowIndex">
            <td v-for="(cell, cellIndex) in row" :key="cellIndex">{{ formatCell(cell) }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="props.value.truncated || props.value.row_count !== undefined" class="display-meta">
        {{ props.value.row_count !== undefined ? `共 ${props.value.row_count} 行` : '' }}{{ props.value.truncated ? ' · 已截断预览' : '' }}
      </p>
    </div>

    <div v-else-if="props.value.kind === 'series'" class="display-table-wrap">
      <p class="display-meta">
        {{ props.value.name ? `Series: ${props.value.name}` : 'Series' }}{{ props.value.dtype ? ` · ${props.value.dtype}` : '' }}{{ shapeText ? ` · shape ${shapeText}` : '' }}
      </p>
      <table class="display-table compact">
        <thead><tr><th>index</th><th>value</th></tr></thead>
        <tbody>
          <tr v-for="row in seriesRows" :key="String(row[0])">
            <td>{{ row[0] }}</td>
            <td>{{ formatCell(row[1]) }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="props.value.truncated" class="display-meta">已截断预览</p>
    </div>

    <div v-else-if="props.value.kind === 'ndarray' || props.value.kind === 'tensor'" class="display-structured">
      <p class="display-meta">
        {{ props.value.kind }}{{ shapeText ? ` · shape ${shapeText}` : '' }}{{ props.value.dtype ? ` · ${props.value.dtype}` : '' }}{{ props.value.device ? ` · ${props.value.device}` : '' }}
      </p>
      <pre>{{ stringify(props.value.values ?? props.value.repr) }}</pre>
    </div>

    <div v-else-if="props.value.kind === 'error'" class="display-structured error">
      <pre>{{ props.value.message || props.value.repr || props.fallback }}</pre>
    </div>

    <div v-else class="display-structured">
      <pre>{{ fallbackText }}</pre>
    </div>
  </div>
  <pre v-else>{{ props.fallback }}</pre>
</template>
