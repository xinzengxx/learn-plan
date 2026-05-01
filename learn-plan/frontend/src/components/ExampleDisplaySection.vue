<script setup lang="ts">
import type { RuntimeExampleDisplay, DatasetTableDescription } from '../types'
import DisplayValueView from './DisplayValueView.vue'

const props = defineProps<{
  examples?: RuntimeExampleDisplay[]
}>()

const MAX_CELL_CHARS = 160

function formatCell(value: unknown): string {
  if (value === undefined || value === null) return ''
  const text = typeof value === 'string' ? value : JSON.stringify(value)
  return text.length > MAX_CELL_CHARS ? `${text.slice(0, MAX_CELL_CHARS)}…` : text
}

function visibleTables(example: RuntimeExampleDisplay): DatasetTableDescription[] {
  return example.input_tables || []
}
</script>

<template>
  <article v-if="props.examples?.length" class="statement-card compact example-display-section">
    <p class="eyebrow">Examples</p>
    <h3>示例</h3>
    <div class="example-list">
      <section v-for="example in props.examples" :key="example.title" class="example-card polished">
        <header class="example-card-header">
          <span>{{ example.title }}</span>
        </header>

        <div class="example-io-grid polished">
          <div class="example-io-block input-block polished">
            <strong>示例输入</strong>
            <div v-if="example.input_kind === 'tables'" class="example-table-inputs">
              <section v-for="table in visibleTables(example)" :key="table.name" class="example-table-input-card">
                <h4>{{ table.display_name || table.name }}</h4>
                <p class="display-meta"><code>{{ table.name }}</code></p>
                <div v-if="table.preview?.columns?.length" class="display-table-wrap">
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
              </section>
            </div>
            <dl v-else class="example-parameter-list">
              <div v-for="parameter in example.input_parameters" :key="parameter.name" class="example-parameter-row">
                <dt>{{ parameter.name }}</dt>
                <dd><DisplayValueView :value="parameter.valueDisplay" /></dd>
              </div>
            </dl>
          </div>

          <div class="example-io-block output-block polished">
            <strong>示例输出</strong>
            <DisplayValueView :value="example.outputDisplay" />
          </div>
        </div>

        <div v-if="example.explanation" class="rich-text example-explanation">
          {{ example.explanation }}
        </div>
      </section>
    </div>
  </article>
</template>
