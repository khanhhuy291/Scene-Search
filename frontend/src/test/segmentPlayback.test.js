import { describe, expect, it, vi } from 'vitest'
import { enforceSegmentEnd, playSegment, restartSegmentOnPlay } from '../lib/segmentPlayback'

describe('full-video segment playback', () => {
  const player = () => ({ duration: 40, currentTime: 0, play: vi.fn().mockResolvedValue(), pause: vi.fn() })

  it('seeks exactly to the requested segment start', () => {
    const video = player()
    playSegment(video, 12, 18)
    expect(video.currentTime).toBe(12)
    expect(video.play).toHaveBeenCalledOnce()
  })

  it('pauses and clamps at the segment end rather than playing the rest of the source', () => {
    const video = player()
    video.currentTime = 18.15
    enforceSegmentEnd(video, 12, 18)
    expect(video.currentTime).toBe(18)
    expect(video.pause).toHaveBeenCalledOnce()
  })

  it('replays from the segment start when play is pressed at its end', () => {
    const video = player()
    video.currentTime = 18
    restartSegmentOnPlay(video, 12, 18)
    expect(video.currentTime).toBe(12)
  })

  it('does not pause while inside the segment and clamps end to actual duration', () => {
    const video = player()
    video.currentTime = 15
    enforceSegmentEnd(video, 12, 18)
    expect(video.pause).not.toHaveBeenCalled()
    video.currentTime = 41
    enforceSegmentEnd(video, 12, 50)
    expect(video.currentTime).toBe(40)
  })
})
