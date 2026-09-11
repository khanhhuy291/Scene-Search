/**
 * Scene search API client.
 *
 * Relative URLs throughout: the dev server proxies /api to the backend and in
 * production the two are served from one origin. Failures surface as SearchError
 * so a down API is not silently replaced by the mock corpus.
 */

const SEARCH_URL = '/api/v1/search'

export class SearchError extends Error {
  constructor(message, { status } = {}) {
    super(message)
    this.name = 'SearchError'
    this.status = status
  }
}

/**
 * Format a timestamp span the way the cards display it.
 */
export const formatTimestamp = (startSeconds, endSeconds) => {
  const clock = (value) => {
    const total = Math.max(0, Math.floor(value))
    const hours = Math.floor(total / 3600)
    const minutes = Math.floor((total % 3600) / 60)
    const seconds = total % 60
    const mm = String(minutes).padStart(2, '0')
    const ss = String(seconds).padStart(2, '0')
    return hours > 0 ? `${hours}:${mm}:${ss}` : `${mm}:${ss}`
  }
  if (endSeconds == null || Number.isNaN(endSeconds)) {
    return clock(startSeconds)
  }
  return `${clock(startSeconds)} – ${clock(endSeconds)}`
}

/** Turn a snake_case concept name into something readable in a chip. */
export const humanizeConcept = (concept) => concept.replace(/_/g, ' ')

/** Attach media fragment `#t=start,end` for bound segment playback. */
export const withTimeFragment = (url, startSeconds, endSeconds) => {
  if (!url) return url
  const base = url.split('#')[0]
  const start = Math.max(0, Number(startSeconds) || 0)
  if (endSeconds != null && !Number.isNaN(Number(endSeconds)) && Number(endSeconds) > start) {
    return `${base}#t=${start},${Number(endSeconds)}`
  }
  if (start > 0) return `${base}#t=${start}`
  return base
}

const mapMoment = (moment, fallback, index, { isPrimary = false } = {}) => {
  const startSeconds = Number(
    moment.video_second ??
    moment.ts_start_s ??
    moment.timestamp_s ??
    moment.startSeconds ??
    fallback.startSeconds ??
    0
  )
  const rawEnd = moment.ts_end_s ?? moment.endSeconds
  const endSeconds =
    rawEnd != null && !Number.isNaN(Number(rawEnd)) && Number(rawEnd) > startSeconds
      ? Number(rawEnd)
      : null
  return {
    id: moment.id || `${fallback.id}_m${index}`,
    startSeconds,
    endSeconds,
    videoSecond: startSeconds,
    timestamp: formatTimestamp(startSeconds, endSeconds),
    caption: moment.caption || moment.description || fallback.description,
    thumbnail: moment.thumbnail_url || moment.thumbnail || fallback.thumbnail,
    frameNo: moment.frame_no ?? moment.frameNo ?? null,
    weather: moment.weather || null,
    timeOfDay: moment.time_of_day || null,
    sceneType: moment.scene_type || null,
    retrievalTags: moment.retrieval_tags || [],
    isPrimary: Boolean(moment.is_primary ?? isPrimary),
    relevance: moment.relevance || (isPrimary ? 'best match' : 'also matched')
  }
}

/**
 * Build the list of prompt-relevant moments inside one video.
 * Prefers API `matched_moments`. Does not invent sibling timestamps — a fake
 * +7.5s offset made every keyframe look like it was the same clip window.
 */
export const buildMatchingMoments = (result, primary) => {
  const raw = result.matching_moments || result.matched_moments || result.related_moments || []
  if (raw.length > 0) {
    const hasPrimaryFlag = raw.some((moment) => moment.is_primary)
    return raw.map((moment, index) =>
      mapMoment(moment, primary, index, {
        isPrimary: hasPrimaryFlag ? Boolean(moment.is_primary) : index === 0
      })
    )
  }

  return [
    mapMoment(
      {
        id: primary.id,
        video_second: primary.videoSecond,
        ts_start_s: primary.startSeconds,
        ts_end_s: primary.endSeconds,
        caption: primary.description,
        thumbnail_url: primary.thumbnail,
        frame_no: primary.frameNo,
        weather: primary.weather,
        time_of_day: primary.timeOfDay,
        scene_type: primary.sceneType,
        retrieval_tags: primary.retrievalTags,
        is_primary: true,
        relevance: 'best match'
      },
      primary,
      0,
      { isPrimary: true }
    )
  ]
}

/**
 * Adapt one API result to the shape the cards render.
 */
export const toScene = (result, index) => {
  const startSeconds = Number(result.video_second ?? result.ts_start_s ?? 0)
  const endSeconds = result.ts_end_s != null ? Number(result.ts_end_s) : null
  const basePreview = result.preview_url || null
  const primary = {
    id: result.id,
    rank: index + 1,
    videoId: result.video_id,
    description: result.caption || 'No description available for this keyframe.',
    timestamp: formatTimestamp(startSeconds, endSeconds),
    startSeconds,
    endSeconds,
    videoSecond: startSeconds,
    thumbnail: result.thumbnail_url,
    previewUrl: withTimeFragment(basePreview, startSeconds),
    previewBaseUrl: basePreview ? basePreview.split('#')[0] : null,
    frameNo: result.frame_no,
    keyframesMatched: result.keyframes_matched ?? result.matched ?? 1,
    totalKeyframes: result.total_keyframes ?? result.total_kf ?? 8,
    confirmed: result.confirmed ?? [],
    denied: result.denied ?? [],
    contradictionNote: result.contradiction_note || null,
    weather: result.weather || result.metadata?.scene?.weather || null,
    timeOfDay: result.time_of_day || result.metadata?.scene?.time_of_day || null,
    sceneType: result.scene_type || result.metadata?.scene?.scene_type || result.metadata?.scene?.road_type || null,
    retrievalTags: result.retrieval_tags || result.metadata?.retrieval_tags || [],
    metadata: result.metadata || null,
    objects: result.objects || [],
    score: result.score != null ? Number(result.score) : null,
    scoreBreakdown: result.score_breakdown || null,
    isReranked: Boolean(result.score_breakdown?.rerank != null),
    rerankScore: result.score_breakdown?.rerank != null ? Number(result.score_breakdown.rerank) : (result.score != null ? Number(result.score) : null)
  }
  primary.matchingMoments = buildMatchingMoments(result, primary)
  primary.keyframesMatched = Math.max(primary.keyframesMatched, primary.matchingMoments.length)
  if (primary.totalKeyframes < primary.keyframesMatched) {
    primary.totalKeyframes = primary.keyframesMatched
  }
  return primary
}

const mapResponse = (body) => ({
  scenes: (body.results || []).map(toScene),
  totalVideos: body.total ?? 0,
  totalKeyframes: body.total_keyframes ?? 0,
  interpretedQuery: body.interpreted_query || '',
  requiredConcepts: body.required_concepts || [],
  excludedConcepts: body.excluded_concepts || [],
  unmatchedTerms: body.unmatched_terms || [],
  exhaustive: Boolean(body.exhaustive),
  signalsUsed: body.signals_used || [],
  belowThreshold: Boolean(body.below_threshold),
  unconfirmedConcepts: body.unconfirmed_concepts || [],
  nextCursor: body.next_cursor || null,
  tookMs: body.took_ms ?? 0,
  modelVersion: body.model_version || '',
  degraded: Boolean(body.degraded),
  source: body.source || 'api'
})

/**
 * Run a search against the live API. Network and HTTP errors raise SearchError.
 */
export const searchScenes = async ({
  query,
  limit = 24,
  cursor = null,
  mode = 'hybrid',
  require: requireConcepts = null,
  exclude = null,
  explain = false,
  signal
} = {}) => {
  let response
  try {
    response = await fetch(SEARCH_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query,
        limit,
        cursor,
        mode,
        explain,
        ...(requireConcepts !== null ? { require: requireConcepts } : {}),
        ...(exclude !== null ? { exclude } : {})
      }),
      signal
    })
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new SearchError(
      'Search API is unreachable. Is the backend running on port 8000?',
      { status: 0 }
    )
  }

  if (!response.ok) {
    let detail = `Search failed with status ${response.status}`
    try {
      const body = await response.json()
      if (body?.detail) {
        detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
      }
    } catch {
      // Keep the status-based message when the body is not JSON.
    }
    throw new SearchError(detail, { status: response.status })
  }

  const body = await response.json()
  return mapResponse(body)
}

/**
 * Why a search came back empty, phrased for the person who ran it.
 */
export const explainEmptyResult = ({
  query,
  belowThreshold,
  unconfirmedConcepts = [],
  excludedConcepts = []
} = {}) => {
  if (unconfirmedConcepts.length > 0) {
    const concepts = unconfirmedConcepts.map(humanizeConcept).join(', ')
    return `No keyframe in the corpus is described as containing ${concepts}. Try removing that from the query.`
  }
  if (belowThreshold) {
    return `Nothing in this corpus resembles “${query}”. The footage is dashcam and street video, so subjects outside that return no results rather than the closest unrelated clip.`
  }
  if (excludedConcepts.length > 0) {
    const concepts = excludedConcepts.map(humanizeConcept).join(', ')
    return `Matches were found, but every one of them was ruled out by the exclusion of ${concepts}. Remove that filter to see them.`
  }
  return 'No matching scenes found. Try describing the scene differently.'
}
