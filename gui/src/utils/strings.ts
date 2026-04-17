/** Returns the last two path segments with a leading ellipsis. */
export function shortId(id: string): string {
  const parts = id.split('/')
  return parts.length > 2 ? '…/' + parts.slice(-2).join('/') : id
}
