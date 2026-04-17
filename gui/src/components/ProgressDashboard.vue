<template>
  <div class="progress-dashboard">
    <div class="stat-row">
      <div class="stat">
        <span class="stat-value converted">{{ store.stats.converted }}</span>
        <span class="stat-label">converted</span>
      </div>
      <div class="stat">
        <span class="stat-value in-progress">{{ store.stats.inProgress }}</span>
        <span class="stat-label">in progress</span>
      </div>
      <div class="stat">
        <span class="stat-value needs-review">{{ store.stats.needsReview }}</span>
        <span class="stat-label">needs review</span>
      </div>
    </div>
    <div class="status-badge" :class="store.status">{{ store.status }}</div>
  </div>
</template>

<script setup lang="ts">
import { useRunStore } from '../store'
const store = useRunStore()
</script>

<style scoped>
.progress-dashboard { padding: 16px; border-bottom: 1px solid #333; }
.stat-row { display: flex; gap: 32px; }
.stat { display: flex; flex-direction: column; align-items: center; }
.stat-value { font-size: 28px; font-weight: bold; }
.stat-value.converted { color: #4ade80; }
.stat-value.in-progress { color: #60a5fa; }
.stat-value.needs-review { color: #f97316; }
.stat-label { font-size: 11px; color: #888; margin-top: 2px; }
.status-badge { display: inline-block; margin-top: 12px; padding: 2px 10px;
  border-radius: 4px; font-size: 12px; background: #1a1a1a; border: 1px solid #444; }
.status-badge.running { border-color: #60a5fa; color: #60a5fa; }
.status-badge.complete { border-color: #4ade80; color: #4ade80; }
.status-badge.interrupted { border-color: #f97316; color: #f97316; }
.status-badge.aborted { border-color: #f87171; color: #f87171; }
.status-badge.paused { border-color: #a78bfa; color: #a78bfa; }
</style>
