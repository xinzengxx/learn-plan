<script setup lang="ts">
import { computed } from 'vue'
import { renderRichText } from '../renderers/richText'
import type { DemoQuestion, ProblemPanelMode, SubmitRecord } from '../types'
import DatasetDescriptionSection from './DatasetDescriptionSection.vue'
import ExampleDisplaySection from './ExampleDisplaySection.vue'
import StatusPanel from './StatusPanel.vue'
import SubmitHistory from './SubmitHistory.vue'

const props = defineProps<{
  question: DemoQuestion
  mode: ProblemPanelMode
  records: SubmitRecord[]
}>()

const emit = defineEmits<{
  changeMode: [mode: ProblemPanelMode]
}>()

const questionTypeMeta = computed(() => {
  if (props.question.type === 'code') return { label: '代码题', code: 'CODE' }
  if (props.question.type === 'sql') return { label: 'SQL 题', code: 'MYSQL' }
  if (props.question.type === 'single_choice') return { label: '选择题 · 单选', code: 'SINGLE' }
  if (props.question.type === 'multiple_choice') return { label: '选择题 · 多选', code: 'MULTI' }
  return { label: '判断题', code: 'TRUE / FALSE' }
})
const descriptionHtml = computed(() => renderRichText(props.question.description))
const inputSpecHtml = computed(() => renderRichText(props.question.inputSpec))
const outputSpecHtml = computed(() => renderRichText(props.question.outputSpec))
const constraintItems = computed(() => props.question.constraints || [])
const exampleItems = computed(() => props.question.exampleDisplays || [])
</script>

<template>
  <section class="problem-panel">
    <header class="problem-titlebar">
      <div>
        <p class="eyebrow title-meta">
          <span :class="['difficulty-badge', props.question.difficultyLevel]">{{ props.question.difficulty }}</span>
          <span>· {{ props.question.tags.join(' / ') }}</span>
        </p>
        <h2>{{ props.question.order }}. {{ props.question.title }}</h2>
      </div>
      <span class="type-badge">
        <span class="type-badge-label">{{ questionTypeMeta.label }}</span>
        <span class="type-badge-code">{{ questionTypeMeta.code }}</span>
      </span>
    </header>

    <nav class="tabbar" aria-label="题目信息切换">
      <button :class="{ active: props.mode === 'description' }" type="button" @click="emit('changeMode', 'description')">题目描述</button>
      <button :class="{ active: props.mode === 'history' }" type="button" @click="emit('changeMode', 'history')">提交记录</button>
      <button :class="{ active: props.mode === 'status' }" type="button" @click="emit('changeMode', 'status')">答题状态</button>
    </nav>

    <div class="tab-content">
      <div v-if="props.mode === 'description'" class="description-layout">
        <article class="statement-card hero">
          <p class="eyebrow">Problem Statement</p>
          <h3>题目详细描述</h3>
          <div class="rich-text" v-html="descriptionHtml" />
        </article>

        <DatasetDescriptionSection :dataset="props.question.datasetDescription" />

        <div class="io-spec-grid">
          <article v-if="props.question.inputSpec" class="io-spec-card input-spec">
            <p class="eyebrow">Input</p>
            <h3>输入说明</h3>
            <div class="rich-text" v-html="inputSpecHtml" />
          </article>
          <article v-if="props.question.outputSpec" class="io-spec-card output-spec">
            <p class="eyebrow">Output</p>
            <h3>输出说明</h3>
            <div class="rich-text" v-html="outputSpecHtml" />
          </article>
        </div>

        <article v-if="constraintItems.length" class="statement-card compact">
          <p class="eyebrow">Limits</p>
          <h3>约束条件</h3>
          <ul class="constraint-list">
            <li v-for="constraint in constraintItems" :key="constraint" v-html="renderRichText(constraint)" />
          </ul>
        </article>

        <ExampleDisplaySection :examples="exampleItems" />
      </div>
      <SubmitHistory v-else-if="props.mode === 'history'" :records="props.records" />
      <StatusPanel v-else :question="props.question" :records="props.records" />
    </div>
  </section>
</template>
