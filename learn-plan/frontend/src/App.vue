<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import AnswerWorkspace from './components/AnswerWorkspace.vue'
import ResultToast from './components/ResultToast.vue'
import ProblemInfoTabs from './components/ProblemInfoTabs.vue'
import Sidebar from './components/Sidebar.vue'
import { useRuntimeStore } from './store/runtimeStore'

const store = useRuntimeStore()
const themeMode = ref<'paper' | 'ink'>('ink')
const layoutSizes = reactive({ sidebar: 300, problem: 560 })
const shellStyle = computed(() => ({
  '--sidebar-width': `${store.state.sidebarCollapsed ? 82 : layoutSizes.sidebar}px`,
  '--problem-width': `${layoutSizes.problem}px`,
}))

const hasNextQuestion = computed(() => {
  const idx = store.state.questions.findIndex((q) => q.id === store.state.activeQuestionId)
  return idx >= 0 && idx < store.state.questions.length - 1
})

function goNextQuestion() {
  const idx = store.state.questions.findIndex((q) => q.id === store.state.activeQuestionId)
  if (idx >= 0 && idx < store.state.questions.length - 1) {
    store.selectQuestion(store.state.questions[idx + 1].id)
  }
  store.toastRecord.value = null
}

const activeUnsureIndices = computed(() =>
  store.state.progress.questions?.[store.state.activeQuestionId]?.unsure || []
)

const activeHasAttempts = computed(() =>
  (store.state.progress.questions?.[store.state.activeQuestionId]?.stats?.attempts || 0) > 0
)

function dismissToast() {
  store.toastRecord.value = null
}

function toggleThemeMode() {
  themeMode.value = themeMode.value === 'paper' ? 'ink' : 'paper'
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function startColumnResize(target: 'sidebar' | 'problem', event: PointerEvent) {
  const startX = event.clientX
  const startSidebar = layoutSizes.sidebar
  const startProblem = layoutSizes.problem

  function handlePointerMove(moveEvent: PointerEvent) {
    const delta = moveEvent.clientX - startX
    if (target === 'sidebar') {
      layoutSizes.sidebar = clamp(startSidebar + delta, 220, 420)
      return
    }
    layoutSizes.problem = clamp(startProblem + delta, 440, 820)
  }

  function stopResize() {
    window.removeEventListener('pointermove', handlePointerMove)
    window.removeEventListener('pointerup', stopResize)
  }

  window.addEventListener('pointermove', handlePointerMove)
  window.addEventListener('pointerup', stopResize, { once: true })
}
</script>

<template>
  <main class="demo-shell" :data-theme="themeMode" :style="shellStyle" :class="{ 'sidebar-collapsed': store.state.sidebarCollapsed }">
    <Sidebar
      :questions="store.state.questions"
      :active-question-id="store.state.activeQuestionId"
      :collapsed="store.state.sidebarCollapsed"
      :latest-records="store.latestRecordsByQuestion.value"
      :title="store.state.topic || '题集'"
      :subtitle="store.state.title || ''"
      @select="store.selectQuestion"
      @toggle="store.toggleSidebar"
    />

    <div
      class="column-resizer"
      role="separator"
      aria-label="调整题目列表宽度"
      @pointerdown="startColumnResize('sidebar', $event)"
    />

    <section v-if="store.state.loading" class="problem-panel empty-runtime-state">
      <div class="empty-state">正在加载题集...</div>
    </section>
    <section v-else-if="store.state.error" class="problem-panel empty-runtime-state">
      <div class="empty-state">题集加载失败：{{ store.state.error }}</div>
    </section>
    <section v-else-if="!store.activeQuestion.value" class="problem-panel empty-runtime-state">
      <div class="empty-state">当前题集没有可展示的题目。</div>
    </section>
    <ProblemInfoTabs
      v-else
      :question="store.activeQuestion.value"
      :mode="store.state.panelMode"
      :records="store.activeHistory.value"
      @change-mode="store.setPanelMode"
    />

    <div
      class="column-resizer"
      role="separator"
      aria-label="调整题目描述和作答区宽度"
      @pointerdown="startColumnResize('problem', $event)"
    />

    <AnswerWorkspace
      v-if="store.activeQuestion.value"
      :question="store.activeQuestion.value"
      :theme-mode="themeMode"
      :unsure-indices="activeUnsureIndices"
      :has-attempts="activeHasAttempts"
      @toggle-theme="toggleThemeMode"
      @update-draft="store.updateDraft"
      @toggle-choice="store.toggleChoice"
      @toggle-unsure="store.toggleUnsure"
      @skip="store.skipCurrentQuestion"
      @run="store.runCurrentQuestion"
      @submit="store.submitCurrentQuestion"
    />
  </main>
  <ResultToast
    v-if="store.toastRecord.value"
    :record="store.toastRecord.value"
    :has-next-question="hasNextQuestion"
    @close="dismissToast"
    @next="goNextQuestion"
  />
</template>
