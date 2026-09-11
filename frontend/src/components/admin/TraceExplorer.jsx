import React, { useState, useEffect, useCallback, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Activity,
  Search,
  RefreshCw,
  Trash2,
  ChevronDown,
  ChevronUp,
  Flame,
  Copy,
  Check,
  Zap
} from 'lucide-react'
import { getSystemTraces, clearSystemTraces } from '../../api/admin'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'

const CATEGORY_CONFIG = {
  parser: {
    label: 'PARSER',
    color: '#3B82F6',
    bg: 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/30'
  },
  llm: {
    label: 'LLM GUARD & HyDE',
    color: '#F59E0B',
    bg: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30'
  },
  embedding: {
    label: 'VLM EMBEDDING',
    color: '#10B981',
    bg: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30'
  },
  vectordb: {
    label: 'QDRANT HNSW',
    color: '#8B5CF6',
    bg: 'bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/30'
  },
  rerank: {
    label: 'CROSS-RERANKER',
    color: '#FF5500',
    bg: 'bg-[#FF5500]/10 text-[#FF5500] border-[#FF5500]/30'
  },
  cache: {
    label: 'STORAGE & CACHE',
    color: '#06B6D4',
    bg: 'bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 border-cyan-500/30'
  },
  chat: {
    label: 'VLM SYNTHESIS',
    color: '#EC4899',
    bg: 'bg-pink-500/10 text-pink-600 dark:text-pink-400 border-pink-500/30'
  }
}

export const TraceExplorer = () => {
  const { token } = useAuth()
  const { addToast } = useToast()
  const [data, setData] = useState({ stats: null, traces: [] })
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [filterType, setFilterType] = useState('ALL')
  const [searchQuery, setSearchQuery] = useState('')
  const [expandedId, setExpandedId] = useState(null)
  const [copiedId, setCopiedId] = useState(null)

  const fetchTraces = useCallback(async () => {
    if (!token) return
    try {
      const res = await getSystemTraces(token, {
        limit: 50,
        traceType: filterType === 'ALL' ? undefined : filterType.toLowerCase()
      })
      setData(res)
    } catch {
      // quiet fail on background polling
    }
  }, [token, filterType])

  useEffect(() => {
    fetchTraces()
  }, [fetchTraces])

  // Polling interval
  useEffect(() => {
    if (!autoRefresh) return
    const timer = setInterval(() => {
      fetchTraces()
    }, 3000)
    return () => clearInterval(timer)
  }, [autoRefresh, fetchTraces])

  const handleClear = async () => {
    if (!window.confirm('Bạn có chắc chắn muốn xóa toàn bộ lịch sử trace trong RAM?')) return
    try {
      await clearSystemTraces(token)
      addToast('Đã xóa toàn bộ dữ liệu Trace thành công', 'success')
      fetchTraces()
    } catch (err) {
      addToast(err.message || 'Lỗi khi xóa Trace', 'error')
    }
  }

  const handleCopy = (text, id) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const filteredTraces = useMemo(() => {
    return (data.traces || []).filter((t) => {
      if (searchQuery.trim() === '') return true
      const q = searchQuery.toLowerCase()
      return (
        t.query?.toLowerCase().includes(q) ||
        t.id?.toLowerCase().includes(q) ||
        t.route?.toLowerCase().includes(q)
      )
    })
  }, [data.traces, searchQuery])

  const stats = data.stats || {
    total_traces: 0,
    avg_latency_ms: 0,
    p50_latency_ms: 0,
    p95_latency_ms: 0,
    error_rate_pct: 0
  }

  return (
    <div className="space-y-6 font-mono animate-fadeIn">
      {/* Top Banner & Observability KPIs */}
      <div className="bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] p-6 sm:p-8 space-y-6">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b-2 border-black">
          <div className="space-y-1">
            <div className="inline-flex items-center gap-2 px-2.5 py-0.5 bg-[#FF5500] text-black text-[10px] font-black uppercase border border-black shadow-[1.5px_1.5px_0px_0px_#000]">
              <Flame className="w-3 h-3" />
              <span>APM & TRACE WATERFALL ENGINE</span>
            </div>
            <h2 className="text-2xl font-black uppercase tracking-tight text-black dark:text-white">
              TRUY VẾT THỜI GIAN THỰC & ĐỘ TRỄ (PIPELINE TRACES)
            </h2>
            <p className="text-xs text-stone-600 dark:text-stone-400 font-sans">
              Phân rã mili-giây từng tầng: Query Parser → LLM Visual-HyDE → Qwen/SigLIP Vector → Qdrant HNSW → Reranker.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={`px-3 py-1.5 text-xs font-black uppercase border-2 border-black transition-all flex items-center gap-1.5 shadow-[2px_2px_0px_0px_#000] ${
                autoRefresh
                  ? 'bg-[#00D084] text-black'
                  : 'bg-stone-200 dark:bg-stone-800 text-stone-600 dark:text-stone-400'
              }`}
            >
              <Activity className={`w-3.5 h-3.5 ${autoRefresh ? 'animate-pulse' : ''}`} />
              <span>{autoRefresh ? 'LIVE (3S)' : 'PAUSED'}</span>
            </button>

            <button
              type="button"
              onClick={fetchTraces}
              className="p-2 bg-black hover:bg-[#FF5500] text-white hover:text-black border-2 border-black shadow-[2px_2px_0px_0px_#000] transition-all cursor-pointer"
              title="Làm mới ngay"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>

            <button
              type="button"
              onClick={handleClear}
              className="p-2 bg-red-100 hover:bg-red-600 text-red-900 hover:text-white border-2 border-black shadow-[2px_2px_0px_0px_#000] transition-all cursor-pointer"
              title="Xóa bộ đệm Trace"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* 4 KPI Metrics Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="p-4 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black shadow-[3px_3px_0px_0px_#000]">
            <span className="text-[10px] font-black uppercase text-stone-500">TỔNG LƯỢT TRACE TRONG RAM</span>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-3xl font-black text-black dark:text-white">{stats.total_traces}</span>
              <span className="text-[10px] text-stone-500">/ 100 max</span>
            </div>
          </div>

          <div className="p-4 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black shadow-[3px_3px_0px_0px_#000]">
            <span className="text-[10px] font-black uppercase text-stone-500">ĐỘ TRỄ TRUNG BÌNH (AVG)</span>
            <div className="flex items-baseline gap-1 mt-1">
              <span className="text-3xl font-black text-[#FF5500]">{stats.avg_latency_ms}</span>
              <span className="text-xs font-bold text-stone-500">ms</span>
            </div>
          </div>

          <div className="p-4 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black shadow-[3px_3px_0px_0px_#000]">
            <span className="text-[10px] font-black uppercase text-stone-500">P50 / P95 LATENCY</span>
            <div className="flex items-baseline gap-1.5 mt-1">
              <span className="text-2xl font-black text-[#00D084]">{stats.p50_latency_ms}</span>
              <span className="text-xs text-stone-400">/</span>
              <span className="text-2xl font-black text-amber-500">{stats.p95_latency_ms}</span>
              <span className="text-[10px] font-bold text-stone-500">ms</span>
            </div>
          </div>

          <div className="p-4 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black shadow-[3px_3px_0px_0px_#000]">
            <span className="text-[10px] font-black uppercase text-stone-500">TỶ LỆ LỖI / DEGRADED</span>
            <div className="flex items-baseline gap-1 mt-1">
              <span className={`text-3xl font-black ${stats.error_rate_pct > 5 ? 'text-red-600' : 'text-emerald-600'}`}>
                {stats.error_rate_pct}%
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-4 bg-white dark:bg-[#1C1A17] border-2 border-black shadow-[4px_4px_0px_0px_#000]">
        <div className="flex items-center gap-2">
          {['ALL', 'SEARCH', 'CHAT'].map((type) => (
            <button
              key={type}
              type="button"
              onClick={() => setFilterType(type)}
              className={`px-3 py-1 text-xs font-black uppercase border transition-all cursor-pointer ${
                filterType === type
                  ? 'bg-black text-white dark:bg-white dark:text-black border-black shadow-[1.5px_1.5px_0px_0px_#FF5500]'
                  : 'bg-stone-100 dark:bg-stone-800 text-stone-600 dark:text-stone-400 border-stone-300 dark:border-stone-700 hover:border-black'
              }`}
            >
              {type === 'ALL' ? 'TẤT CẢ' : type === 'SEARCH' ? '🔍 TÌM KIẾM' : '💬 CHATBOT'}
            </button>
          ))}
        </div>

        <div className="relative flex-1 max-w-md">
          <Search className="w-3.5 h-3.5 text-stone-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Lọc theo câu truy vấn hoặc Trace ID..."
            className="w-full bg-[#F7F4EE] dark:bg-stone-900 border border-black px-8 py-1.5 text-xs text-black dark:text-white placeholder:text-stone-400 outline-none shadow-[2px_2px_0px_0px_#000]"
          />
        </div>
      </div>

      {/* Traces List */}
      {filteredTraces.length === 0 ? (
        <div className="p-12 bg-white dark:bg-[#1C1A17] border-2 border-black shadow-[4px_4px_0px_0px_#000] text-center space-y-3">
          <Activity className="w-8 h-8 text-[#FF5500] mx-auto animate-bounce" />
          <h3 className="text-sm font-black uppercase text-black dark:text-white">CHƯA CÓ DỮ LIỆU TRACE TRONG RAM</h3>
          <p className="text-xs text-stone-600 dark:text-stone-400 font-sans max-w-md mx-auto">
            Thực hiện một vài thao tác tìm kiếm phân cảnh trên trang Tìm kiếm hoặc trò chuyện với Chatbot để xem luồng phân rã mili-giây tại đây.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredTraces.map((trace) => {
            const isExpanded = expandedId === trace.id
            const totalMs = trace.total_duration_ms || 1

            return (
              <div
                key={trace.id}
                className="bg-white dark:bg-[#1C1A17] border-2 border-black shadow-[4px_4px_0px_0px_#000] overflow-hidden transition-all"
              >
                {/* Header Row */}
                <div
                  onClick={() => setExpandedId(isExpanded ? null : trace.id)}
                  className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-3 cursor-pointer hover:bg-[#F7F4EE]/50 dark:hover:bg-stone-900/50 transition-colors"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span
                      className={`px-2 py-0.5 text-[10px] font-black uppercase border shrink-0 ${
                        trace.type === 'chat'
                          ? 'bg-pink-100 dark:bg-pink-950/50 text-pink-700 dark:text-pink-300 border-pink-600'
                          : 'bg-blue-100 dark:bg-blue-950/50 text-blue-700 dark:text-blue-300 border-blue-600'
                      }`}
                    >
                      {trace.type === 'chat' ? 'CHATBOT' : 'SEARCH'}
                    </span>

                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-black text-black dark:text-white truncate">
                          "{trace.query}"
                        </span>
                        <span className="text-[10px] text-stone-400 font-normal shrink-0">
                          {trace.timestamp ? new Date(trace.timestamp).toLocaleTimeString() : ''}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 text-[10px] text-stone-500 mt-0.5">
                        <span>ID: {trace.id}</span>
                        {trace.route && (
                          <span className="px-1.5 bg-stone-100 dark:bg-stone-800 border border-stone-300 dark:border-stone-700 text-[9px] font-bold uppercase">
                            ROUTE: {trace.route}
                          </span>
                        )}
                        {trace.metrics?.matches_count != null && (
                          <span>· {trace.metrics.matches_count} matches</span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Waterfall Bar Preview + Total Latency */}
                  <div className="flex items-center gap-4 shrink-0">
                    {/* Compact Waterfall Bar */}
                    <div className="hidden sm:flex items-center w-48 h-3 bg-stone-100 dark:bg-stone-800 border border-black overflow-hidden">
                      {trace.spans?.map((span, idx) => {
                        const pct = Math.max(2, (span.duration_ms / totalMs) * 100)
                        const cfg = CATEGORY_CONFIG[span.category] || { color: '#6B7280' }
                        return (
                          <div
                            key={idx}
                            style={{ width: `${pct}%`, backgroundColor: cfg.color }}
                            className="h-full"
                            title={`${span.name}: ${span.duration_ms}ms (${pct.toFixed(1)}%)`}
                          />
                        )
                      })}
                    </div>

                    <div className="text-right">
                      <span className="px-2.5 py-1 bg-black text-[#FF5500] font-black text-xs border border-black shadow-[1.5px_1.5px_0px_0px_#000]">
                        {trace.total_duration_ms} ms
                      </span>
                    </div>

                    <div className="text-stone-500">
                      {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    </div>
                  </div>
                </div>

                {/* Expanded Waterfall Breakdown & Inspector */}
                <AnimatePresence>
                  {isExpanded && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="border-t-2 border-black p-5 bg-[#F7F4EE]/30 dark:bg-stone-900/30 space-y-4 font-mono text-xs"
                    >
                      <div className="flex items-center justify-between pb-2 border-b border-stone-300 dark:border-stone-800">
                        <span className="font-black uppercase text-stone-700 dark:text-stone-300 flex items-center gap-2">
                          <Zap className="w-4 h-4 text-[#FF5500]" />
                          GANTT WATERFALL TIMELINE & SUB-SPANS
                        </span>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => handleCopy(JSON.stringify(trace, null, 2), trace.id)}
                            className="px-2.5 py-1 bg-white dark:bg-stone-800 border border-black hover:bg-black hover:text-white text-[10px] font-bold uppercase transition-all flex items-center gap-1 cursor-pointer"
                          >
                            {copiedId === trace.id ? <Check className="w-3 h-3 text-[#00D084]" /> : <Copy className="w-3 h-3" />}
                            <span>{copiedId === trace.id ? 'ĐÃ COPY' : 'COPY JSON'}</span>
                          </button>
                        </div>
                      </div>

                      {/* Spans Gantt Table */}
                      <div className="space-y-2">
                        {trace.spans?.map((span, sIdx) => {
                          const cfg = CATEGORY_CONFIG[span.category] || {
                            label: span.category?.toUpperCase(),
                            color: '#6B7280',
                            bg: 'bg-stone-100 text-stone-700'
                          }
                          const startPct = Math.min(95, (span.start_offset_ms / totalMs) * 100)
                          const widthPct = Math.max(3, (span.duration_ms / totalMs) * 100)

                          return (
                            <div
                              key={sIdx}
                              className="p-3 bg-white dark:bg-[#1C1A17] border border-black shadow-[2px_2px_0px_0px_#000] space-y-2"
                            >
                              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                                <div className="flex items-center gap-2 min-w-0">
                                  <span className={`px-2 py-0.5 text-[9px] font-black uppercase border ${cfg.bg}`}>
                                    {cfg.label}
                                  </span>
                                  <span className="font-bold text-black dark:text-white text-xs truncate">
                                    {span.name}
                                  </span>
                                </div>
                                <div className="flex items-center gap-3 text-[11px] text-stone-500 font-bold shrink-0">
                                  <span>BẮT ĐẦU: +{span.start_offset_ms}ms</span>
                                  <span className="text-[#FF5500] font-black">
                                    {span.duration_ms} ms ({((span.duration_ms / totalMs) * 100).toFixed(1)}%)
                                  </span>
                                </div>
                              </div>

                              {/* Gantt Bar Visualization */}
                              <div className="w-full h-2.5 bg-stone-100 dark:bg-stone-800 border border-stone-300 dark:border-stone-700 relative overflow-hidden">
                                <div
                                  style={{
                                    left: `${startPct}%`,
                                    width: `${widthPct}%`,
                                    backgroundColor: cfg.color
                                  }}
                                  className="absolute top-0 bottom-0 shadow-sm"
                                />
                              </div>

                              {/* Span Details (if any) */}
                              {span.details && Object.keys(span.details).length > 0 && (
                                <div className="p-2.5 bg-[#F7F4EE] dark:bg-stone-900 border border-stone-300 dark:border-stone-800 text-[10px] space-y-1">
                                  {Object.entries(span.details).map(([k, v]) => (
                                    <div key={k} className="flex items-start gap-2">
                                      <span className="font-bold text-stone-500 uppercase shrink-0">{k}:</span>
                                      <span className="text-black dark:text-stone-200 break-all font-mono">
                                        {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                                      </span>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          )
                        })}
                      </div>

                      {/* Trace Metrics Summary */}
                      {trace.metrics && Object.keys(trace.metrics).length > 0 && (
                        <div className="p-3 bg-white dark:bg-[#1C1A17] border border-black text-[11px] flex flex-wrap items-center gap-4">
                          <span className="font-black uppercase text-[#FF5500]">METRICS:</span>
                          {Object.entries(trace.metrics).map(([k, v]) => (
                            <span key={k} className="text-stone-600 dark:text-stone-400">
                              <strong className="text-black dark:text-white uppercase">{k}:</strong>{' '}
                              {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                            </span>
                          ))}
                        </div>
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
