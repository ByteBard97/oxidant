<template>
  <div class="flex-1 flex flex-col overflow-y-auto bg-surface-container-low p-8 gap-8 font-mono">
    <TierStats />
    <ModuleGrid />
    <ErrorPatternTable />
  </div>
</template>

<script setup lang="ts">
import TierStats from './TierStats.vue'
import ModuleGrid from './ModuleGrid.vue'
import ErrorPatternTable from './ErrorPatternTable.vue'
</script>
