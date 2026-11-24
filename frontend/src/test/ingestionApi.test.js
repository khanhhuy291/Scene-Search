import { afterEach, expect, it, vi } from 'vitest'
import { uploadVideo } from '../api/ingestion'

afterEach(() => vi.unstubAllGlobals())

it('uploads through the same-origin API once and preserves enqueue errors', async () => {
  const requests = []
  class FakeRequest {
    constructor() { this.upload = {}; requests.push(this) }
    open = vi.fn()
    setRequestHeader = vi.fn()
    send = vi.fn(() => {
      this.status = 503
      this.response = { detail: 'Unable to enqueue ingestion task' }
      this.onload()
    })
  }
  vi.stubGlobal('XMLHttpRequest', FakeRequest)
  const fetch = vi.fn()
  vi.stubGlobal('fetch', fetch)
  await expect(uploadVideo(new File(['video'], 'clip.mp4'), null, 'token'))
    .rejects.toThrow('Unable to enqueue ingestion task')
  expect(requests).toHaveLength(1)
  expect(requests[0].open).toHaveBeenCalledWith('POST', '/api/v1/ingest/upload')
  expect(requests[0].setRequestHeader).toHaveBeenCalledWith('Authorization', 'Bearer token')
  expect(fetch).not.toHaveBeenCalled()
})
