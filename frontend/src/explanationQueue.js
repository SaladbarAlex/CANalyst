// Finish the current request on Stop so its result remains visible and cached.
// A capture/model change invalidates UI updates as well as future requests.
export async function runExplanationQueue({ items, isStopped, isCurrent, explain, onResult }) {
  for (let index = 0; index < items.length; index++) {
    if (isStopped() || !isCurrent()) return
    await explain(items[index])
    if (!isCurrent()) return
    await onResult(items[index], index)
  }
}
