<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import type { SubmitRecord } from '../types'

const props = defineProps<{
  record: SubmitRecord
  hasNextQuestion: boolean
}>()

const emit = defineEmits<{
  close: []
  next: []
}>()

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div class="result-toast-overlay" @click.self="emit('close')">
    <div class="result-toast" role="dialog" aria-label="提交结果">
      <div class="result-toast-header" :class="props.record.status">
        <span class="result-toast-icon">{{ props.record.status === 'passed' ? '✓' : props.record.status === 'skipped' ? '→' : '✗' }}</span>
        <div>
          <p class="result-toast-title">{{ props.record.status === 'passed' ? '通过' : props.record.status === 'skipped' ? '已跳过' : '未通过' }}</p>
          <p class="result-toast-subtitle">
            <template v-if="props.record.action === 'skip'">跳过此题</template>
            <template v-else>{{ props.record.action === 'submit' ? '提交答案' : '运行代码' }}</template>
             · {{ props.record.createdAt }}
          </p>
        </div>
      </div>

      <div class="result-toast-body">
        <div v-if="props.record.testCases.length" class="result-toast-stat">
          <span class="result-toast-stat-label">测试用例</span>
          <span class="result-toast-stat-value">
            {{ props.record.testCases.filter((c) => c.passed).length }}/{{ props.record.testCases.length }} 通过
          </span>
        </div>
        <div v-if="props.record.message" class="result-toast-stat">
          <span class="result-toast-stat-label">{{ props.record.status === 'passed' ? '结果' : props.record.status === 'skipped' ? '说明' : '原因' }}</span>
          <span class="result-toast-stat-value">{{ props.record.message }}</span>
        </div>
      </div>

      <div class="result-toast-footer">
        <button v-if="props.hasNextQuestion" class="toast-btn primary" @click="emit('next')">下一题</button>
        <button class="toast-btn" @click="emit('close')">关闭</button>
      </div>
    </div>
  </div>
</template>
