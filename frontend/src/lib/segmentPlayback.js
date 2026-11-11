// Bounds are seconds on the complete source video's timeline.
export const segmentBounds = (start, end, duration = Infinity) => {
  const durationLimit = Number.isFinite(duration) && duration > 0 ? duration : Infinity
  const from = Math.min(Math.max(0, Number(start) || 0), durationLimit)
  const candidate = end == null ? Infinity : Number(end)
  const to = Number.isFinite(candidate) && candidate >= from
    ? Math.min(candidate, durationLimit)
    : durationLimit
  return { start: from, end: to }
}

export const playSegment = (video, start, end) => {
  const bounds = segmentBounds(start, end, video.duration)
  video.currentTime = bounds.start
  if (bounds.end <= bounds.start) {
    video.pause()
    return
  }
  video.play()?.catch(() => {})
}

export const enforceSegmentEnd = (video, start, end) => {
  const bounds = segmentBounds(start, end, video.duration)
  if (video.currentTime >= bounds.end) {
    video.pause()
    if (video.currentTime !== bounds.end) video.currentTime = bounds.end
  } else if (video.currentTime < bounds.start) {
    video.currentTime = bounds.start
  }
}

export const restartSegmentOnPlay = (video, start, end) => {
  const bounds = segmentBounds(start, end, video.duration)
  if (bounds.end <= bounds.start) {
    video.pause()
    return
  }
  if (video.currentTime < bounds.start || video.currentTime >= bounds.end) {
    video.currentTime = bounds.start
  }
}
