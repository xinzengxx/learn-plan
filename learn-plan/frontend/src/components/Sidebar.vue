<script setup lang="ts">
import type { DemoQuestion, SubmitRecord } from '../types'

const props = defineProps<{
  questions: DemoQuestion[]
  activeQuestionId: string
  collapsed: boolean
  latestRecords: Record<string, SubmitRecord>
  title?: string
  subtitle?: string
}>()

const emit = defineEmits<{
  select: [questionId: string]
  toggle: []
}>()

function typeLabel(type: DemoQuestion['type']) {
  return {
    code: '代码',
    single_choice: '单选',
    multiple_choice: '多选',
    true_false: '判断',
  }[type]
}

function statusLabel(status: DemoQuestion['status']) {
  return {
    not_started: '未做',
    draft: '草稿',
    passed: '通过',
    failed: '待改',
    skipped: '已跳过',
  }[status]
}

function latestRecord(questionId: string) {
  return props.latestRecords[questionId]
}

function failedCount(questionId: string) {
  return latestRecord(questionId)?.testCases.filter((testCase) => !testCase.passed).length || 0
}

function passedCount(questionId: string) {
  return latestRecord(questionId)?.testCases.filter((testCase) => testCase.passed).length || 0
}
</script>

<template>
  <aside class="sidebar" :class="{ collapsed: props.collapsed }">
    <div class="sidebar-header">
      <div v-if="!props.collapsed">
        <p v-if="props.subtitle" class="eyebrow">{{ props.subtitle }}</p>
        <h1>{{ props.title || '题集' }}</h1>
      </div>
      <button class="icon-button" type="button" @click="emit('toggle')">
        {{ props.collapsed ? '展开' : '收起' }}
      </button>
    </div>

    <div class="question-list">
      <button
        v-for="question in props.questions"
        :key="question.id"
        class="question-item"
        :class="{ active: question.id === props.activeQuestionId }"
        type="button"
        @click="emit('select', question.id)"
      >
        <span class="question-index">{{ question.order }}</span>
        <span v-if="!props.collapsed" class="question-meta">
          <strong>{{ question.title }}</strong>
          <span class="question-tags">
            <em>{{ typeLabel(question.type) }}</em>
            <em :class="['difficulty-badge', question.difficultyLevel]">{{ question.difficulty }}</em>
            <em :class="['status-pill', question.status]">{{ statusLabel(question.status) }}</em>
            <em v-if="latestRecord(question.id)" class="test-tag">
              测试 {{ passedCount(question.id) }}/{{ latestRecord(question.id).testCases.length }} 通过
            </em>
            <em v-if="failedCount(question.id)" class="test-tag failed">{{ failedCount(question.id) }} 未过</em>
          </span>
        </span>
      </button>
    </div>
  </aside>
</template>
