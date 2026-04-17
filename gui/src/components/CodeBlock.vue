<template>
  <div class="code-block">
    <!-- Loading shimmer -->
    <div v-if="loading" class="text-zinc-600 text-[11px] font-mono p-3 italic">highlighting...</div>
    <!-- Highlighted HTML injected by Shiki -->
    <div v-else class="shiki-wrap" v-html="html" />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { getHighlighter } from '../composables/useHighlighter'

const props = withDefaults(defineProps<{
  code: string
  lang: 'typescript' | 'rust'
}>(), {
  lang: 'typescript',
})

const html    = ref('')
const loading = ref(true)

async function highlight() {
  loading.value = true
  try {
    const h = await getHighlighter()
    html.value = h.codeToHtml(props.code, {
      lang:  props.lang,
      theme: 'salvaged-terminal',
    })
  } catch {
    // Fallback: plain pre-formatted text
    html.value = `<pre class="fallback">${escapeHtml(props.code)}</pre>`
  } finally {
    loading.value = false
  }
}

function escapeHtml(s: string): string {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
}

onMounted(highlight)
watch(() => [props.code, props.lang], highlight)
</script>

<style>
/* Strip Shiki's default wrapper styles so we control the shell */
.shiki-wrap pre {
  background: transparent !important;
  margin: 0;
  padding: 12px;
  overflow-x: auto;
  font-family: ui-monospace, 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 11px;
  line-height: 1.65;
  tab-size: 2;
}

.shiki-wrap code {
  font-family: inherit;
  font-size: inherit;
}

.shiki-wrap .line {
  display: block;
}

/* Plain fallback */
.code-block .fallback {
  font-family: ui-monospace, monospace;
  font-size: 11px;
  line-height: 1.65;
  color: #dcd7d0;
  padding: 12px;
  margin: 0;
  white-space: pre-wrap;
}
</style>
