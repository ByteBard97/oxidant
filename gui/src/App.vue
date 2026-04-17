<template>
  <div class="app-layout">
    <header class="app-header">
      <span class="app-title">oxidant</span>
      <span class="app-subtitle">TS → Rust translation harness</span>
    </header>

    <main class="app-main">
      <aside class="sidebar">
        <RunControls />
        <ProgressDashboard />
      </aside>
      <section class="feed-area">
        <LiveNodeFeed />
      </section>
    </main>

    <!-- Review panel overlays from the right when an interrupt fires -->
    <ReviewPanel />
  </div>
</template>

<script setup lang="ts">
import RunControls from './components/RunControls.vue'
import ProgressDashboard from './components/ProgressDashboard.vue'
import LiveNodeFeed from './components/LiveNodeFeed.vue'
import ReviewPanel from './components/ReviewPanel.vue'
</script>

<style>
.app-layout { display: flex; flex-direction: column; height: 100vh; }
.app-header {
  display: flex; align-items: baseline; gap: 12px;
  padding: 12px 20px; border-bottom: 1px solid #333; background: #0a0a0a;
}
.app-title { font-size: 18px; font-weight: bold; color: #a78bfa; }
.app-subtitle { font-size: 12px; color: #555; }
.app-main { display: flex; flex: 1; overflow: hidden; }
.sidebar { width: 340px; border-right: 1px solid #333; overflow-y: auto; flex-shrink: 0; }
.feed-area { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
</style>
