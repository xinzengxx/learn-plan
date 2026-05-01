<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import type { DemoQuestion, SubmitRecord } from '../types'
import DisplayValueView from './DisplayValueView.vue'

const props = defineProps<{
  question: DemoQuestion
  records: SubmitRecord[]
}>()

const latestRecord = computed(() => props.records[0])
const passedCount = computed(() => latestRecord.value?.testCases?.filter((c) => c.passed).length || 0)
const totalCount = computed(() => latestRecord.value?.testCases?.length || 0)
const firstFailedIndex = computed(() => activeCases.value.findIndex((c) => 'passed' in c && !c.passed))

const activeCaseIndex = ref(0)
const detailKey = ref(0)

watch(() => latestRecord.value, () => {
  // Auto-focus first failed case, otherwise Case 1
  const failIdx = firstFailedIndex.value
  activeCaseIndex.value = failIdx >= 0 ? failIdx : 0
  detailKey.value++
})

const activeCases = computed(() => {
  if (!latestRecord.value) return []
  if (latestRecord.value.action === 'run') return latestRecord.value.runCases || latestRecord.value.testCases || []
  return latestRecord.value.testCases || []
})

const testCase = computed(() => activeCases.value?.[activeCaseIndex.value])
const hasStructuredRunCases = computed(() => latestRecord.value?.action === 'run' && (latestRecord.value.runCases || []).some((item) => Boolean(item.inputDisplay || item.expectedDisplay || item.actualDisplay)))

const resultLabel = computed(() => {
  if (!latestRecord.value) return ''
  if (latestRecord.value.status === 'passed') return '通过'
  if (latestRecord.value.action === 'run') return '运行结果'
  return '未通过'
})

const caseSummary = computed(() => {
  if (!activeCases.value.length) return ''
  if (latestRecord.value?.action === 'run') return `展示 ${activeCases.value.length} 个运行样例`
  const testCases = activeCases.value.filter((c) => 'passed' in c)
  const passed = testCases.filter((c) => c.passed).length
  const total = testCases.length
  if (passed === total) return `全部 ${total} 个用例通过`
  const firstFail = testCases.findIndex((c) => !c.passed)
  return `${passed}/${total} 通过 · 首个失败: Case ${firstFail + 1}`
})

function selectCase(index: number) {
  if (index === activeCaseIndex.value) return
  activeCaseIndex.value = index
  detailKey.value++
}
</script>

<template>
  <section class="panel-section">
    <!-- No result yet -->
    <div v-if="!latestRecord" class="empty-state compact">点击运行或提交查看结果</div>

    <template v-else>
      <!-- Result header -->
      <div class="result-header" :class="latestRecord.status">
        <div class="result-status">
          <span class="result-icon">{{ latestRecord.status === 'passed' ? '✓' : '✗' }}</span>
          <span class="result-label">{{ resultLabel }}</span>
          <span v-if="latestRecord.action === 'submit' && totalCount" class="result-score">
            {{ passedCount }}/{{ totalCount }}
          </span>
        </div>
        <span class="result-meta">{{ latestRecord.action === 'run' ? '运行' : '提交' }} · {{ latestRecord.createdAt }}</span>
      </div>

      <!-- Error summary -->
      <div v-if="latestRecord.status === 'failed' && latestRecord.failure_types?.length" class="error-summary">
        <span v-for="ft in latestRecord.failure_types" :key="ft" class="error-tag">{{ ft }}</span>
      </div>

      <!-- Case summary -->
      <div v-if="caseSummary" class="case-summary">{{ caseSummary }}</div>

      <!-- Case tabs -->
      <ul v-if="activeCases.length" class="case-tabs">
        <li v-for="(c, index) in activeCases" :key="index">
          <button
            :class="['case-tab', { active: activeCaseIndex === index }, 'passed' in c && c.passed === true ? 'passed' : ('passed' in c && c.passed === false ? 'failed' : '')]"
            @click="selectCase(index)"
          >
            <span class="case-tab-icon">{{ 'passed' in c && c.passed === true ? '✓' : 'passed' in c && c.passed === false ? '✗' : '·' }}</span>
            Case {{ index + 1 }}
          </button>
        </li>
      </ul>

      <!-- Case detail -->
      <Transition name="case-fade" mode="out-in">
        <article v-if="testCase" :key="detailKey" class="case-detail">
          <div class="case-io">
            <div class="case-io-row case-io-input">
              <span class="case-io-label">输入</span>
              <DisplayValueView :value="testCase.inputDisplay" :fallback="testCase.input" />
            </div>
            <div v-if="testCase.expectedDisplay || ('expected' in testCase && testCase.expected !== undefined)" class="case-io-row case-io-expected">
              <span class="case-io-label">预期</span>
              <DisplayValueView :value="testCase.expectedDisplay" :fallback="testCase.expected" />
            </div>
            <div class="case-io-row case-io-actual" :class="{ 'case-io-match': 'passed' in testCase && testCase.passed === true, 'case-io-mismatch': 'passed' in testCase && testCase.passed === false }">
              <span class="case-io-label">实际返回值</span>
              <DisplayValueView :value="testCase.actualDisplay" :fallback="testCase.actual || '(无返回值)'" />
            </div>
            <div v-if="testCase.stdout" class="case-io-row case-io-stdout">
              <span class="case-io-label">stdout</span>
              <pre>{{ testCase.stdout }}</pre>
            </div>
            <div v-if="testCase.stderr" class="case-io-row case-io-stdout">
              <span class="case-io-label">stderr</span>
              <pre>{{ testCase.stderr }}</pre>
            </div>
          </div>
          <div v-if="testCase.error" class="case-error">
            <span class="case-io-label">错误</span>
            <pre>{{ testCase.error }}</pre>
          </div>
          <div v-if="testCase.traceback" class="case-error">
            <span class="case-io-label">traceback</span>
            <pre>{{ testCase.traceback }}</pre>
          </div>
        </article>
      </Transition>

      <!-- Terminal output for run results -->
      <div v-if="latestRecord.terminalOutput && latestRecord.action === 'run' && !hasStructuredRunCases" class="case-terminal">
        <pre>{{ latestRecord.terminalOutput }}</pre>
      </div>
    </template>
  </section>
</template>
