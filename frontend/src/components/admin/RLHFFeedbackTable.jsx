import React, { useEffect, useState } from 'react'
import {
  Download,
  Sparkles,
  Search,
  ArrowUpDown,
  Layers,
  Eye,
  X,
  FileJson,
  RefreshCw
} from 'lucide-react'
import { fetchRLHFFeedback, fetchRLHFStats, downloadRLHFDataset } from '../../api/feedback'
import { useToast } from '../../context/ToastContext'

export const RLHFFeedbackTable = () => {
  const { addToast } = useToast()
  const [loading, setLoading] = useState(true)
  const [feedbackList, setFeedbackList] = useState([])
  const [total, setTotal] = useState(0)
  const [stats, setStats] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [page, setPage] = useState(1)
  const pageSize = 10

  const [selectedItem, setSelectedItem] = useState(null)
  const [isExporting, setIsExporting] = useState(false)

  const loadData = async () => {
    setLoading(true)
    try {
      const [feedbacks, statData] = await Promise.all([
        fetchRLHFFeedback({ limit: pageSize, offset: (page - 1) * pageSize, q: searchQuery }),
        fetchRLHFStats()
      ])
      setFeedbackList(feedbacks.items || [])
      setTotal(feedbacks.total || 0)
      setStats(statData)
    } catch (err) {
      addToast(err.message || 'Error loading RLHF feedback data', 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, searchQuery])

  const handleExport = async (format) => {
    setIsExporting(true)
    try {
      await downloadRLHFDataset(format)
      addToast(`Downloaded ${format.toUpperCase()} dataset successfully!`, 'success')
    } catch (err) {
      addToast(err.message || 'Failed to download dataset', 'error')
    } finally {
      setIsExporting(false)
    }
  }

  const totalPages = Math.ceil(total / pageSize) || 1

  return (
    <div className="space-y-6">
      {/* Metrics Banner */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-surface-elevated border border-border-base p-4 rounded-lg">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-indigo-500/10 text-indigo-400 rounded-md">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs text-text-muted">Total Submissions</p>
              <p className="text-xl font-bold text-text-primary">{stats?.total_submissions || 0}</p>
            </div>
          </div>
        </div>

        <div className="bg-surface-elevated border border-border-base p-4 rounded-lg">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-emerald-500/10 text-emerald-400 rounded-md">
              <Search className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs text-text-muted">Unique Queries</p>
              <p className="text-xl font-bold text-text-primary">{stats?.total_unique_queries || 0}</p>
            </div>
          </div>
        </div>

        <div className="bg-surface-elevated border border-border-base p-4 rounded-lg">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-amber-500/10 text-amber-400 rounded-md">
              <Layers className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs text-text-muted">Annotated Items</p>
              <p className="text-xl font-bold text-text-primary">{stats?.total_reordered_items || 0}</p>
            </div>
          </div>
        </div>

        <div className="bg-surface-elevated border border-border-base p-4 rounded-lg">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-500/10 text-blue-400 rounded-md">
              <ArrowUpDown className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs text-text-muted">Pairwise Pairs</p>
              <p className="text-xl font-bold text-text-primary">{stats?.total_pairwise_preferences || 0}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Toolbar & Actions */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 bg-surface-elevated border border-border-base p-4 rounded-lg">
        <div className="relative flex-1 w-full max-w-md">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            type="text"
            placeholder="Search queries..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value)
              setPage(1)
            }}
            className="w-full pl-9 pr-4 py-2 bg-surface border border-border-base rounded-md text-sm text-text-primary focus:outline-none focus:border-brand-primary"
          />
        </div>

        <div className="flex items-center gap-3 w-full sm:w-auto">
          <button
            onClick={() => loadData()}
            className="p-2 bg-surface hover:bg-surface-hover border border-border-base rounded-md text-text-muted hover:text-text-primary"
            title="Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>

          <button
            onClick={() => handleExport('pairwise')}
            disabled={isExporting || total === 0}
            className="flex items-center gap-2 px-3 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-md text-sm font-medium transition"
          >
            <FileJson className="w-4 h-4" />
            Export Pairwise (DPO / Cross-Encoder)
          </button>

          <button
            onClick={() => handleExport('listwise')}
            disabled={isExporting || total === 0}
            className="flex items-center gap-2 px-3 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white rounded-md text-sm font-medium transition"
          >
            <Download className="w-4 h-4" />
            Export Listwise (Qwen Reranker)
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="bg-surface-elevated border border-border-base rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-surface border-b border-border-base text-text-muted text-xs uppercase">
              <tr>
                <th className="px-4 py-3">Search Query</th>
                <th className="px-4 py-3">Mode</th>
                <th className="px-4 py-3">Annotator</th>
                <th className="px-4 py-3">Items Count</th>
                <th className="px-4 py-3">Created At</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-base">
              {loading ? (
                <tr>
                  <td colSpan="6" className="px-4 py-8 text-center text-text-muted">
                    Loading RLHF feedback...
                  </td>
                </tr>
              ) : feedbackList.length === 0 ? (
                <tr>
                  <td colSpan="6" className="px-4 py-8 text-center text-text-muted">
                    No RLHF ranking feedback found. Annotators can submit reordered rankings directly from the Search page.
                  </td>
                </tr>
              ) : (
                feedbackList.map((item) => (
                  <tr key={item.id} className="hover:bg-surface-hover/50 transition">
                    <td className="px-4 py-3 font-medium text-text-primary max-w-xs truncate">
                      "{item.query}"
                    </td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-0.5 text-xs rounded bg-surface border border-border-base text-text-secondary">
                        {item.mode}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-text-secondary">
                      {item.user_email || 'Anonymous'}
                    </td>
                    <td className="px-4 py-3 text-text-secondary">
                      {item.reordered_ranking?.length || 0} scenes
                    </td>
                    <td className="px-4 py-3 text-text-muted text-xs">
                      {new Date(item.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => setSelectedItem(item)}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-brand-primary bg-brand-primary/10 hover:bg-brand-primary/20 rounded transition"
                      >
                        <Eye className="w-3.5 h-3.5" />
                        Inspect Rerank
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-border-base bg-surface text-xs text-text-muted">
            <div>
              Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, total)} of {total} entries
            </div>
            <div className="flex gap-2">
              <button
                disabled={page === 1}
                onClick={() => setPage((p) => p - 1)}
                className="px-3 py-1 bg-surface-elevated border border-border-base rounded hover:bg-surface-hover disabled:opacity-50"
              >
                Previous
              </button>
              <button
                disabled={page === totalPages}
                onClick={() => setPage((p) => p + 1)}
                className="px-3 py-1 bg-surface-elevated border border-border-base rounded hover:bg-surface-hover disabled:opacity-50"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Inspect Modal */}
      {selectedItem && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
          <div className="bg-surface-elevated border border-border-base rounded-xl max-w-3xl w-full max-h-[85vh] flex flex-col shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between p-4 border-b border-border-base">
              <div>
                <h3 className="font-semibold text-text-primary text-base">RLHF Re-ranking Inspection</h3>
                <p className="text-xs text-text-muted mt-0.5">Query: "{selectedItem.query}"</p>
              </div>
              <button
                onClick={() => setSelectedItem(null)}
                className="p-1 hover:bg-surface rounded text-text-muted hover:text-text-primary"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-4 overflow-y-auto space-y-4 flex-1">
              {selectedItem.notes && (
                <div className="p-3 bg-surface border border-border-base rounded-md text-xs text-text-secondary">
                  <span className="font-medium text-text-primary">Annotator Notes:</span> {selectedItem.notes}
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Original Ranking */}
                <div className="border border-border-base rounded-lg p-3 bg-surface">
                  <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
                    Original Search Order
                  </h4>
                  <div className="space-y-2">
                    {(selectedItem.original_ranking || []).map((scene, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between p-2 rounded bg-surface-elevated border border-border-base text-xs"
                      >
                        <div className="flex items-center gap-2">
                          <span className="w-5 h-5 rounded-full bg-border-base text-text-muted flex items-center justify-center font-bold">
                            {idx + 1}
                          </span>
                          <span className="truncate max-w-[180px] font-mono text-text-primary">
                            {scene.scene_id}
                          </span>
                        </div>
                        {scene.score != null && (
                          <span className="text-text-muted font-mono">{Number(scene.score).toFixed(3)}</span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Reordered Ranking */}
                <div className="border border-emerald-500/30 rounded-lg p-3 bg-emerald-500/5">
                  <h4 className="text-xs font-semibold text-emerald-400 uppercase tracking-wider mb-2">
                    Human Preferred Order (Target)
                  </h4>
                  <div className="space-y-2">
                    {(selectedItem.reordered_ranking || []).map((scene, idx) => {
                      const origIndex = (selectedItem.original_ranking || []).findIndex(
                        (o) => o.scene_id === scene.scene_id
                      )
                      const diff = origIndex >= 0 ? origIndex - idx : 0

                      return (
                        <div
                          key={idx}
                          className="flex items-center justify-between p-2 rounded bg-surface-elevated border border-emerald-500/20 text-xs"
                        >
                          <div className="flex items-center gap-2">
                            <span className="w-5 h-5 rounded-full bg-emerald-500 text-white flex items-center justify-center font-bold">
                              {idx + 1}
                            </span>
                            <span className="truncate max-w-[180px] font-mono text-text-primary">
                              {scene.scene_id}
                            </span>
                          </div>
                          {diff !== 0 && (
                            <span
                              className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                                diff > 0
                                  ? 'bg-emerald-500/20 text-emerald-400'
                                  : 'bg-rose-500/20 text-rose-400'
                              }`}
                            >
                              {diff > 0 ? `▲${diff}` : `▼${Math.abs(diff)}`}
                            </span>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              </div>
            </div>

            <div className="p-4 border-t border-border-base bg-surface flex justify-end">
              <button
                onClick={() => setSelectedItem(null)}
                className="px-4 py-1.5 bg-surface-elevated border border-border-base rounded-md text-xs font-medium text-text-primary hover:bg-surface-hover"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
