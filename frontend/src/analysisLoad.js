// Load expensive ID details alongside the core views, without making alert
// review wait for them. ID results are published only after a successful core
// load, and every publication checks that the capture/model is still current.
export function loadAnalysisViews({ loadCore, loadIds, isCurrent, isIdsCurrent = isCurrent, onCore, onIds, onIdsError }) {
  const idsResult = Promise.resolve().then(loadIds).then(
    (value) => ({ value }), (error) => ({ error }),
  )
  const coreDone = Promise.resolve().then(loadCore).then((value) => {
    if (isCurrent()) onCore(value)
  })
  const idsDone = coreDone.then(() => idsResult).then((result) => {
    if (!isIdsCurrent()) return
    if ('error' in result) onIdsError(result.error)
    else onIds(result.value)
  }, () => { /* Core failure is handled by its caller; don't publish orphan ID details. */ })
  return { coreDone, idsDone }
}
