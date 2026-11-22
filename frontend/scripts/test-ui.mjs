import { build } from 'esbuild'
import { spawnSync } from 'node:child_process'
const result = await build({
  entryPoints: ['tests/render.test.jsx'], bundle: true, platform: 'node', format: 'cjs',
  jsx: 'automatic', define: { 'import.meta.env': '{}' }, write: false,
})
const run = spawnSync(process.execPath, [], { input: result.outputFiles[0].text, encoding: 'utf8' })
process.stdout.write(run.stdout)
process.stderr.write(run.stderr)
process.exitCode = run.status ?? 1
