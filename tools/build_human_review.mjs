import { readFile, writeFile } from 'node:fs/promises'

const sheet = new URL('../backend/out/claim_review/heldout/sheet.csv', import.meta.url)
const page = new URL('../frontend/public/human-review.html', import.meta.url)
const [csv, html] = await Promise.all([readFile(sheet, 'utf8'), readFile(page, 'utf8')])
if (!csv.startsWith('claim_id,claim,cited_items,label,note')) throw new Error('Unexpected review sheet columns')

const embeddedSheet = /(<script type="application\/json" id="blinded-sheet">\n)  .*?(\n  <\/script>)/s
if (!embeddedSheet.test(html)) throw new Error('Embedded review sheet not found')

const payload = JSON.stringify(csv).replaceAll('<', '\\u003c')
await writeFile(page, html.replace(embeddedSheet, (_, start, end) => `${start}  ${payload}${end}`))
