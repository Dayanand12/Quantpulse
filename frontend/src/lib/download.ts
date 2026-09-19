// Triggers a browser "Save As" for an in-memory Blob (a fetched export,
// a generated CSV, ...) without a server-side redirect or a real <a href>
// pointing at a file that exists on disk.
export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
