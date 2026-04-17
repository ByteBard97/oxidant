import { ref } from 'vue'

const visible      = ref(false)
const message      = ref('')
const title        = ref('')
const confirmLabel = ref('CONFIRM')
let resolver: ((val: boolean) => void) | null = null

export function useConfirm() {
  function confirm(
    msg:   string,
    ttl:   string = 'CONFIRM ACTION',
    label: string = 'CONFIRM',
  ): Promise<boolean> {
    message.value      = msg
    title.value        = ttl
    confirmLabel.value = label
    visible.value      = true
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

  return { visible, message, title, confirmLabel, confirm, accept, cancel }
}
