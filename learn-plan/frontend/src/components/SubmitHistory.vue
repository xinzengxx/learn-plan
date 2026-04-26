<script setup lang="ts">
import type { SubmitRecord } from '../types'

defineProps<{
  records: SubmitRecord[]
}>()

function actionLabel(action: SubmitRecord['action']) {
  return action === 'run' ? '运行' : action === 'skip' ? '跳过' : '提交'
}
</script>

<template>
  <section class="panel-section">
    <div v-if="!records.length" class="empty-state">暂无记录</div>
    <article v-for="record in records" :key="record.id" class="history-card" :class="record.status">
      <div class="history-card-topline">
        <strong>{{ actionLabel(record.action) }}</strong>
        <span>{{ record.createdAt }}</span>
      </div>
      <p>{{ record.message }}</p>
    </article>
  </section>
</template>
