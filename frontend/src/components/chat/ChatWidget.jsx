import React, { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Bot,
  Sparkles,
  X,
  Send,
  Trash2,
  ChevronDown,
  ChevronUp,
  Search,
  Film,
  Clock,
  Layers,
  Image as ImageIcon,
  Play
} from 'lucide-react'
import { sendChatMessageApi } from '../../api/chat'

const QUICK_PROMPTS = [
  'Tìm xe buýt màu vàng rẽ trái lúc trời mưa',
  'Cảnh người đi bộ qua đường vào ban đêm',
  'Xe cảnh sát hoặc cứu thương bật đèn ưu tiên',
  'Xe tải dừng đỗ bên lề đường lúc hoàng hôn'
]

export const ChatWidget = () => {
  const [isOpen, setIsOpen] = useState(false)
  const [input, setInput] = useState('')
  const [limit, setLimit] = useState(3)
  const [loading, setLoading] = useState(false)
  const [expandedReasoning, setExpandedReasoning] = useState({})
  const [selectedVideoScene, setSelectedVideoScene] = useState(null)
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content:
        'Xin chào! Tôi là Trợ lý AI Đa phương thức (VLM) cho hệ thống SceneSearch. Tôi có thể tự động phân tích câu hỏi, lặp và tinh chỉnh truy vấn (paraphrase), đọc ảnh keyframe và trả lời chi tiết kèm video cho bạn!',
      sources: []
    }
  ])

  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)
  const videoRef = useRef(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    if (isOpen) {
      scrollToBottom()
      inputRef.current?.focus()
    }
  }, [isOpen, messages, loading])

  // When video modal opens, seek to timestamp
  useEffect(() => {
    if (selectedVideoScene && videoRef.current) {
      if (selectedVideoScene.timestamp_s) {
        videoRef.current.currentTime = Math.max(0, selectedVideoScene.timestamp_s - 1)
      }
    }
  }, [selectedVideoScene])

  const handleSend = async (textToSend) => {
    const query = (textToSend || input).trim()
    if (!query || loading) return

    const userMessage = { role: 'user', content: query }
    const updatedMessages = [...messages, userMessage]
    setMessages(updatedMessages)
    setInput('')
    setLoading(true)

    try {
      const historyPayload = updatedMessages
        .filter((_, idx) => idx > 0)
        .slice(-6)
        .map((m) => ({ role: m.role, content: m.content }))

      const data = await sendChatMessageApi({
        message: query,
        history: historyPayload,
        limit: Number(limit)
      })

      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: data.reply,
          reasoning: data.reasoning,
          sources: data.sources || [],
          queryUsed: data.query_used,
          queriesTried: data.queries_tried || [],
          iterations: data.iterations || 1
        }
      ])
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `⚠️ Có lỗi xảy ra trong quá trình xử lý: ${err.message}`,
          sources: []
        }
      ])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const toggleReasoning = (idx) => {
    setExpandedReasoning((prev) => ({
      ...prev,
      [idx]: !prev[idx]
    }))
  }

  const clearChat = () => {
    setMessages([
      {
        role: 'assistant',
        content:
          'Đã làm mới cuộc hội thoại! Bạn cần tôi tìm kiếm hoặc phân tích phân cảnh giao thông nào tiếp theo?',
        sources: []
      }
    ])
    setExpandedReasoning({})
  }

  return (
    <>
      {/* Floating Action Button */}
      <AnimatePresence>
        {!isOpen && (
          <motion.button
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0, opacity: 0 }}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={() => setIsOpen(true)}
            className="fixed bottom-6 right-6 z-50 flex items-center gap-3 px-5 py-3.5 bg-amber-500 hover:bg-amber-400 text-stone-950 font-mono font-black uppercase text-xs tracking-wider border-2 border-stone-950 dark:border-amber-400 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_0px_rgba(251,191,36,1)] transition-all cursor-pointer"
          >
            <div className="relative flex items-center justify-center">
              <Bot className="w-5 h-5" />
              <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-emerald-500 rounded-full border border-stone-950 animate-pulse" />
            </div>
            <span>[🤖 AI CHAT ASSISTANT]</span>
          </motion.button>
        )}
      </AnimatePresence>

      {/* Chat Window Drawer / Modal */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: 40, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 40, scale: 0.96 }}
            transition={{ duration: 0.2 }}
            className="fixed bottom-6 right-6 z-50 w-[520px] max-w-[calc(100vw-2rem)] h-[720px] max-h-[calc(100vh-4rem)] flex flex-col bg-[#FAF7F2] dark:bg-[#181512] border-3 border-stone-950 dark:border-[#423b32] shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] dark:shadow-[8px_8px_0px_0px_rgba(251,191,36,0.3)] font-sans overflow-hidden"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 bg-stone-900 text-white border-b-2 border-stone-950 dark:border-[#423b32]">
              <div className="flex items-center gap-2.5">
                <div className="p-1.5 bg-amber-500 text-stone-950 border border-stone-950 font-mono">
                  <Bot className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="font-mono font-black text-xs uppercase tracking-wider text-amber-400 flex items-center gap-1.5">
                    SCENESEARCH QA AGENT
                    <span className="text-[9px] bg-amber-400/20 text-amber-300 px-1.5 py-0.5 border border-amber-400/40">
                      NEMOTRON VLM
                    </span>
                  </h3>
                  <p className="text-[10px] text-stone-400 font-mono">
                    Autonomous Iterative Retrieval & Visual Inspection
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-1">
                <button
                  onClick={clearChat}
                  title="Clear conversation"
                  className="p-1.5 text-stone-400 hover:text-white hover:bg-stone-800 transition-colors border border-transparent hover:border-stone-700"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => setIsOpen(false)}
                  title="Close chat"
                  className="p-1.5 text-stone-400 hover:text-white hover:bg-stone-800 transition-colors border border-transparent hover:border-stone-700"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Message Area */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4 font-mono text-xs">
              {messages.map((msg, idx) => {
                const isAssistant = msg.role === 'assistant'
                const hasReasoning = Boolean(msg.reasoning)
                const isReasoningOpen = expandedReasoning[idx]
                const sources = msg.sources || []
                const queriesTried = msg.queriesTried || []

                return (
                  <div
                    key={idx}
                    className={`flex flex-col ${isAssistant ? 'items-start' : 'items-end'} space-y-1`}
                  >
                    <span className="text-[10px] uppercase font-bold text-stone-500 dark:text-stone-400">
                      {isAssistant ? '🤖 Nemotron Agent' : '👤 You'}
                    </span>

                    <div
                      className={`max-w-[94%] p-3.5 border-2 ${
                        isAssistant
                          ? 'bg-white dark:bg-[#201c18] text-stone-900 dark:text-stone-100 border-stone-950 dark:border-[#423b32] shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] dark:shadow-[3px_3px_0px_0px_rgba(0,0,0,0.5)]'
                          : 'bg-amber-100 dark:bg-amber-950/40 text-stone-950 dark:text-amber-200 border-stone-950 dark:border-amber-700 shadow-[3px_3px_0px_0px_rgba(0,0,0,1)]'
                      }`}
                    >
                      {/* Search Formulation & Paraphrase Badges */}
                      {msg.queryUsed && (
                        <div className="mb-2.5 pb-2 border-b border-dashed border-stone-300 dark:border-stone-700 space-y-1">
                          <div className="flex items-center gap-1.5 text-[11px] text-amber-700 dark:text-amber-400 font-bold">
                            <Search className="w-3.5 h-3.5 flex-shrink-0" />
                            <span>Truy vấn khớp: &quot;{msg.queryUsed}&quot;</span>
                          </div>
                          {queriesTried.length > 1 && (
                            <div className="text-[9px] text-stone-500 dark:text-stone-400 font-mono">
                              🔄 Agent đã thử {queriesTried.length} phiên bản: {queriesTried.map(q => `"${q}"`).join(' ➔ ')}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Reasoning Trace Accordion */}
                      {hasReasoning && (
                        <div className="mb-3 border border-stone-300 dark:border-stone-700 bg-stone-50 dark:bg-stone-900/60">
                          <button
                            onClick={() => toggleReasoning(idx)}
                            className="w-full px-2.5 py-1.5 flex items-center justify-between text-[10px] font-bold uppercase tracking-wider text-stone-600 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
                          >
                            <span className="flex items-center gap-1.5">
                              <Sparkles className="w-3 h-3 text-amber-500" />
                              Quá trình suy luận (Reasoning CoT)
                            </span>
                            {isReasoningOpen ? (
                              <ChevronUp className="w-3 h-3" />
                            ) : (
                              <ChevronDown className="w-3 h-3" />
                            )}
                          </button>
                          {isReasoningOpen && (
                            <div className="p-2.5 text-[10px] text-stone-600 dark:text-stone-400 font-mono whitespace-pre-wrap border-t border-stone-200 dark:border-stone-800 max-h-48 overflow-y-auto">
                              {msg.reasoning}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Main Message Text */}
                      <div className="whitespace-pre-wrap font-sans text-xs leading-relaxed">
                        {msg.content}
                      </div>

                      {/* Cited Visual Scene Cards (Clickable for Video Playback) */}
                      {sources.length > 0 && (
                        <div className="mt-3.5 pt-3 border-t border-stone-200 dark:border-stone-800 space-y-2">
                          <div className="flex items-center justify-between text-[10px] font-bold uppercase text-stone-500 dark:text-stone-400">
                            <span className="flex items-center gap-1">
                              <Layers className="w-3 h-3" />
                              Phân cảnh trích dẫn ({sources.length}):
                            </span>
                            <span className="text-[9px] text-amber-600 dark:text-amber-400">
                              (Bấm vào thẻ để xem video ▶)
                            </span>
                          </div>

                          <div className="grid grid-cols-1 gap-2">
                            {sources.map((src, sIdx) => (
                              <div
                                key={sIdx}
                                onClick={() => setSelectedVideoScene(src)}
                                className="group relative flex gap-2.5 p-2 bg-stone-100 dark:bg-stone-900 border-2 border-stone-300 dark:border-stone-700 hover:border-amber-500 dark:hover:border-amber-400 cursor-pointer transition-all shadow-[2px_2px_0px_0px_rgba(0,0,0,0.1)] hover:shadow-[3px_3px_0px_0px_rgba(251,191,36,0.6)]"
                              >
                                <div className="relative w-24 h-16 bg-stone-950 border border-stone-400 dark:border-stone-700 flex-shrink-0 overflow-hidden flex items-center justify-center">
                                  {src.preview_url ? (
                                    <img
                                      src={src.preview_url}
                                      alt={`Scene ${sIdx + 1}`}
                                      className="w-full h-full object-cover group-hover:scale-105 transition-transform"
                                      onError={(e) => {
                                        e.target.style.display = 'none'
                                      }}
                                    />
                                  ) : (
                                    <ImageIcon className="w-5 h-5 text-stone-600" />
                                  )}
                                  <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity">
                                    <div className="p-1 bg-amber-500 text-stone-950 rounded-full">
                                      <Play className="w-3 h-3 fill-current" />
                                    </div>
                                  </div>
                                </div>

                                <div className="flex-1 min-w-0 font-mono">
                                  <div className="flex items-center justify-between gap-1">
                                    <span className="text-[10px] font-black text-amber-600 dark:text-amber-400 group-hover:underline flex items-center gap-1">
                                      [Scene {sIdx + 1}]
                                      <Play className="w-2.5 h-2.5 fill-current" />
                                    </span>
                                    <span className="text-[9px] px-1 py-0.5 bg-stone-200 dark:bg-stone-800 text-stone-700 dark:text-stone-300 flex items-center gap-0.5 border border-stone-300 dark:border-stone-700">
                                      <Clock className="w-2.5 h-2.5 text-amber-500" />
                                      {src.timestamp || `${src.timestamp_s?.toFixed(1)}s`}
                                    </span>
                                  </div>
                                  <div className="text-[9px] text-stone-500 dark:text-stone-400 truncate mt-0.5">
                                    VID: {src.video_id}
                                  </div>
                                  <p className="text-[10px] font-sans text-stone-700 dark:text-stone-300 line-clamp-2 mt-0.5 leading-tight">
                                    {src.caption || 'No caption provided.'}
                                  </p>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}

              {/* Loading Indicator */}
              {loading && (
                <div className="flex flex-col items-start space-y-1">
                  <span className="text-[10px] uppercase font-bold text-stone-500">
                    🤖 Nemotron Agent
                  </span>
                  <div className="p-3 bg-white dark:bg-[#201c18] border-2 border-stone-950 dark:border-[#423b32] shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] flex items-center gap-2">
                    <div className="w-3 h-3 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
                    <span className="text-xs text-stone-600 dark:text-stone-300 font-mono">
                      Đang tìm kiếm, tinh chỉnh truy vấn & đọc ảnh...
                    </span>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            {/* Quick Prompts */}
            {messages.length <= 2 && !loading && (
              <div className="px-4 py-2 bg-stone-100/80 dark:bg-stone-900/60 border-t border-stone-200 dark:border-stone-800">
                <div className="text-[9px] font-mono font-bold uppercase text-stone-500 dark:text-stone-400 mb-1.5 flex items-center gap-1">
                  <Sparkles className="w-2.5 h-2.5 text-amber-500" />
                  Gợi ý câu hỏi nhanh:
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {QUICK_PROMPTS.map((prompt, pIdx) => (
                    <button
                      key={pIdx}
                      onClick={() => handleSend(prompt)}
                      className="text-[10px] font-mono px-2 py-1 bg-white dark:bg-stone-800 text-stone-700 dark:text-stone-300 border border-stone-300 dark:border-stone-700 hover:border-amber-500 dark:hover:border-amber-400 hover:text-amber-600 transition-colors text-left"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Input Form */}
            <div className="p-3 bg-stone-50 dark:bg-[#1f1b16] border-t-2 border-stone-950 dark:border-[#423b32]">
              <div className="flex items-center justify-between mb-2 text-[10px] font-mono text-stone-500 dark:text-stone-400">
                <span>Shift+Enter xuống dòng, Enter để gửi</span>
                <div className="flex items-center gap-1">
                  <span>Số ảnh đọc:</span>
                  <select
                    value={limit}
                    onChange={(e) => setLimit(e.target.value)}
                    className="bg-white dark:bg-stone-800 text-stone-900 dark:text-white border border-stone-300 dark:border-stone-700 px-1 py-0.5 text-[10px] font-bold"
                  >
                    <option value={2}>2 cảnh</option>
                    <option value={3}>3 cảnh</option>
                    <option value={5}>5 cảnh</option>
                  </select>
                </div>
              </div>

              <div className="flex gap-2">
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Nhập câu hỏi hoặc yêu cầu tìm kiếm phân cảnh..."
                  rows={2}
                  disabled={loading}
                  className="flex-1 p-2.5 bg-white dark:bg-[#141210] text-stone-950 dark:text-stone-100 text-xs font-sans border-2 border-stone-950 dark:border-stone-700 focus:border-amber-500 focus:outline-none resize-none"
                />
                <button
                  onClick={() => handleSend()}
                  disabled={loading || !input.trim()}
                  className="px-4 bg-amber-500 hover:bg-amber-400 disabled:opacity-50 disabled:cursor-not-allowed text-stone-950 font-mono font-bold text-xs border-2 border-stone-950 dark:border-amber-400 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] flex items-center justify-center cursor-pointer transition-all"
                >
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Video Clip Modal Inspector */}
      <AnimatePresence>
        {selectedVideoScene && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
            <div
              className="relative w-full max-w-3xl bg-[#FAF7F2] dark:bg-[#181512] border-3 border-stone-950 dark:border-[#423b32] shadow-[10px_10px_0px_0px_rgba(0,0,0,1)] dark:shadow-[10px_10px_0px_0px_rgba(251,191,36,0.3)] overflow-hidden flex flex-col max-h-[90vh]"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Modal Header */}
              <div className="flex items-center justify-between px-4 py-3 bg-stone-900 text-white border-b-2 border-stone-950 font-mono">
                <div className="flex items-center gap-2">
                  <Film className="w-4 h-4 text-amber-400" />
                  <span className="font-bold text-xs uppercase tracking-wider text-amber-300">
                    XEM VIDEO PHÂN CẢNH ({selectedVideoScene.timestamp})
                  </span>
                </div>
                <button
                  onClick={() => setSelectedVideoScene(null)}
                  className="p-1 hover:bg-stone-800 text-stone-400 hover:text-white transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Video Player */}
              <div className="relative w-full bg-black aspect-video flex items-center justify-center overflow-hidden">
                {selectedVideoScene.clip_url ? (
                  <video
                    ref={videoRef}
                    src={selectedVideoScene.clip_url}
                    controls
                    autoPlay
                    className="w-full h-full object-contain"
                  >
                    Trình duyệt không hỗ trợ thẻ video.
                  </video>
                ) : selectedVideoScene.preview_url ? (
                  <img
                    src={selectedVideoScene.preview_url}
                    alt="Preview"
                    className="w-full h-full object-contain"
                  />
                ) : (
                  <div className="text-stone-400 font-mono text-xs flex flex-col items-center gap-2">
                    <ImageIcon className="w-8 h-8 text-stone-600" />
                    <span>Không có video clip cho phân cảnh này</span>
                  </div>
                )}
              </div>

              {/* Scene Metadata Details */}
              <div className="p-4 space-y-2.5 font-mono text-xs bg-stone-50 dark:bg-[#1a1714] border-t-2 border-stone-950 dark:border-stone-800 overflow-y-auto">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="px-2 py-0.5 bg-amber-400 text-stone-950 font-bold border border-stone-950 text-[10px]">
                    VID: {selectedVideoScene.video_id}
                  </span>
                  <span className="px-2 py-0.5 bg-stone-200 dark:bg-stone-800 text-stone-800 dark:text-stone-200 border border-stone-400 dark:border-stone-700 text-[10px] flex items-center gap-1">
                    <Clock className="w-3 h-3 text-amber-500" />
                    Khung thời gian: {selectedVideoScene.timestamp} ({selectedVideoScene.timestamp_s?.toFixed(1)}s)
                  </span>
                  {selectedVideoScene.score != null && (
                    <span className="px-2 py-0.5 bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300 border border-emerald-500 text-[10px]">
                      Độ khớp: {(selectedVideoScene.score * 100).toFixed(1)}%
                    </span>
                  )}
                </div>

                <div className="p-3 bg-white dark:bg-[#221e1a] border border-stone-300 dark:border-stone-700">
                  <div className="text-[10px] uppercase font-bold text-stone-500 dark:text-stone-400 mb-1">
                    Caption mô tả:
                  </div>
                  <p className="font-sans text-xs text-stone-900 dark:text-stone-100 leading-relaxed">
                    {selectedVideoScene.caption || 'Chưa có caption cho phân cảnh này.'}
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}
      </AnimatePresence>
    </>
  )
}
