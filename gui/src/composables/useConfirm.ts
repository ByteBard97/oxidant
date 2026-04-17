import { ref } from 'vue'

// Module-level singletons so any component can trigger the same modal
const visible = ref(false)
const message = ref('')
const title   = ref('')
let resolver: ((val: boolean) => void) | null = null

export function useConfirm() {
  function confirm(msg: string, ttl = 'CONFIRM ACTION'): Promise<boolean> {
    message.value = msg
    title.value   = ttl
    visible.value = true
    return new Promise(resolve => { resolver = resolve })
  }

  function accept() {
    visible.value = false
    resolver?.(true)
    resolver = null
  }

  function cancel() {
    visible.value = false
    resolver?.(false)
    resolver = null
  }

  return { visible, message, title, confirm, accept, cancel }
}
