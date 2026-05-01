<script setup lang="ts">
import type { DatasetDescription } from '../types'

const props = defineProps<{
  dataset?: DatasetDescription
}>()

const MAX_CELL_CHARS = 160

function formatCell(value: unknown): string {
  if (value === undefined || value === null) return ''
  const text = typeof value === 'string' ? value : JSON.stringify(value)
  return text.length > MAX_CELL_CHARS ? `${text.slice(0, MAX_CELL_CHARS)}…` : text
}
</script>

<template>
  <article v-if="props.dataset?.tables?.length" class="statement-card compact dataset-section">
    <p class="eyebrow">Dataset</p>
    <h3>数据说明</h3>

    <section v-if="props.dataset.relationships?.length" class="dataset-relationships">
      <h4>表关系 / Join keys</h4>
      <ul>
        <li v-for="relationship in props.dataset.relationships" :key="`${relationship.left_table}.${relationship.left_key}-${relationship.right_table}.${relationship.right_key}`">
          <code>{{ relationship.left_table }}.{{ relationship.left_key }}</code>
          <span>→</span>
          <code>{{ relationship.right_table }}.{{ relationship.right_key }}</code>
          <p v-if="relationship.description">{{ relationship.description }}</p>
        </li>
      </ul>
    </section>

    <section v-for="table in props.dataset.tables" :key="table.name" class="dataset-table-card">
      <header class="dataset-table-header">
        <div>
          <h4>{{ table.display_name || table.name }}</h4>
          <p><code>{{ table.name }}</code>{{ table.kind ? ` · ${table.kind}` : '' }}</p>
        </div>
      </header>

      <div class="display-table-wrap">
        <table class="display-table schema-table">
          <thead>
            <tr><th>列名</th><th>类型</th><th>可空</th><th>说明</th></tr>
          </thead>
          <tbody>
            <tr v-for="column in table.columns" :key="column.name">
              <td><code>{{ column.name }}</code></td>
              <td>{{ column.type }}</td>
              <td>{{ column.nullable ? '是' : '否' }}</td>
              <td>{{ column.description || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="table.preview?.columns?.length" class="dataset-preview">
        <h5>Public preview</h5>
        <div class="display-table-wrap">
          <table class="display-table compact">
            <thead>
              <tr>
                <th v-for="column in table.preview.columns" :key="column">{{ column }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, rowIndex) in table.preview.rows" :key="rowIndex">
                <td v-for="(cell, cellIndex) in row" :key="cellIndex">{{ formatCell(cell) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-if="table.preview.truncated" class="display-meta">仅展示前 {{ table.preview.row_limit || table.preview.rows.length }} 行/部分列，public preview 已截断。</p>
      </div>
    </section>
  </article>
</template>
