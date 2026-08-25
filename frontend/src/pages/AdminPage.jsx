import React, { useCallback, useEffect, useState } from 'react'
import { Sidebar } from '../components/layout/Sidebar'
import { DashboardOverview } from '../components/admin/DashboardOverview'
import { UserManagementTable } from '../components/admin/UserManagementTable'
import { CeleryTaskInspector } from '../components/admin/CeleryTaskInspector'
import { CorpusHealth } from '../components/admin/CorpusHealth'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { getAdminTelemetry } from '../api/admin'
import { formatBytes } from '../lib/formatBytes'
import { Shield, Database, HardDrive, RefreshCw } from 'lucide-react'

export const AdminPage = () => {
  const [activeTab, setActiveTab] = useState('corpus')
  const [isCollapsed, setIsCollapsed] = useState(false)
  const { token } = useAuth()
  const { addToast } = useToast()
  const [telemetry, setTelemetry] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    if (!token) return
    setLoading(true)
    try {
      const next = await getAdminTelemetry(token)
      setTelemetry(next)
      setError(null)
    } catch (err) {
      setError(err.message)
      addToast(err.message || 'Failed to load telemetry', 'error')
    } finally {
      setLoading(false)
    }
  }, [addToast, token])

  useEffect(() => {
    refresh()
  }, [refresh])

  const qdrant = telemetry?.qdrant
  const storage = telemetry?.storage

  return (
    <div className="flex min-h-[calc(100vh-4.5rem)] bg-[#F7F4EE] dark:bg-[#141210] transition-colors duration-200 font-sans">
      <Sidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        isCollapsed={isCollapsed}
        setIsCollapsed={setIsCollapsed}
      />

      <main className="flex-1 p-6 md:p-10 max-w-[1700px] mx-auto overflow-y-auto pb-24 space-y-6">
        {/* Top Telemetry Sync Bar */}
        <div className="flex items-center justify-between pb-4 border-b-2 border-black">
          <div className="space-y-1">
            <div className="inline-flex items-center gap-2 px-2.5 py-0.5 bg-white dark:bg-stone-900 border border-black font-mono text-[10px] font-black uppercase text-black dark:text-white shadow-[1.5px_1.5px_0px_0px_#000]">
              <Shield className="w-3 h-3 text-[#FF5500]" />
              <span>ROOT CONSOLE // {activeTab.toUpperCase()}</span>
            </div>
            <h1 className="text-3xl font-black uppercase tracking-tight text-black dark:text-white">
              ADMIN CONTROL CENTER
            </h1>
          </div>

          <button
            type="button"
            onClick={refresh}
            disabled={loading}
            className="px-4 py-2 bg-black hover:bg-[#FF5500] text-white hover:text-black font-mono text-xs font-black uppercase border-2 border-black shadow-[3px_3px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all flex items-center gap-2 cursor-pointer disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>SYNC TELEMETRY</span>
          </button>
        </div>

        {error && activeTab !== 'users' ? (
          <div className="p-4 bg-red-100 dark:bg-red-950/40 border-2 border-red-600 font-mono text-xs font-bold text-red-900 dark:text-red-300">
            [TELEMETRY EXCEPTION] // {error}
          </div>
        ) : null}

        {activeTab === 'corpus' && <CorpusHealth telemetry={telemetry} />}
        {activeTab === 'overview' && (
          <DashboardOverview telemetry={telemetry} onRefresh={refresh} loading={loading} />
        )}
        {activeTab === 'users' && <UserManagementTable />}
        {activeTab === 'tasks' && (
          <CeleryTaskInspector telemetry={telemetry} onRefresh={refresh} loading={loading} />
        )}

        {activeTab === 'vectordb' && (
          <div className="bg-white dark:bg-[#1C1A17] p-6 sm:p-8 border-3 border-black shadow-[6px_6px_0px_0px_#000] space-y-6 font-mono animate-fadeIn">
            <div className="flex items-center justify-between pb-4 border-b-2 border-black">
              <div className="flex items-center gap-2">
                <Database className="w-5 h-5 text-[#FF5500]" />
                <h2 className="text-xl font-black uppercase tracking-tight text-black dark:text-white">
                  QDRANT COLLECTION SCHEMA & VECTORS
                </h2>
              </div>
              <span className="text-xs font-bold uppercase text-[#FF5500]">
                {qdrant?.reachable ? '[STATUS: ONLINE]' : '[STATUS: UNREACHABLE]'}
              </span>
            </div>

            <p className="text-stone-600 dark:text-stone-400 text-xs">
              COLLECTION: <span className="font-bold text-black dark:text-white">{qdrant?.collection || '—'}</span>
              {qdrant?.reachable ? '' : ` · ${qdrant?.detail || 'unreachable'}`}
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs pt-2">
              <div className="p-5 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black shadow-[3px_3px_0px_0px_#000]">
                <span className="text-stone-500 uppercase tracking-widest text-[10px] font-black">
                  TOTAL INDEX POINTS
                </span>
                <p className="text-3xl font-black text-black dark:text-white mt-1">
                  {qdrant?.points_count != null ? qdrant.points_count.toLocaleString() : '—'}
                </p>
              </div>

              <div className="p-5 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black shadow-[3px_3px_0px_0px_#000]">
                <span className="text-stone-500 uppercase tracking-widest text-[10px] font-black">
                  HNSW M PARAMETER
                </span>
                <p className="text-3xl font-black text-[#00D084] mt-1">
                  {qdrant?.hnsw_m != null ? `M=${qdrant.hnsw_m}` : '—'}
                </p>
              </div>

              <div className="p-5 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black shadow-[3px_3px_0px_0px_#000]">
                <span className="text-stone-500 uppercase tracking-widest text-[10px] font-black">
                  EF_CONSTRUCT
                </span>
                <p className="text-3xl font-black text-[#FF5500] mt-1">
                  {qdrant?.ef_construct ?? '—'}
                </p>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'storage' && (
          <div className="bg-white dark:bg-[#1C1A17] p-6 sm:p-8 border-3 border-black shadow-[6px_6px_0px_0px_#000] space-y-6 font-mono animate-fadeIn">
            <div className="flex items-center justify-between pb-4 border-b-2 border-black">
              <div className="flex items-center gap-2">
                <HardDrive className="w-5 h-5 text-[#FF5500]" />
                <h2 className="text-xl font-black uppercase tracking-tight text-black dark:text-white">
                  MINIO S3 OBJECT STORAGE
                </h2>
              </div>
              <span className="text-xs font-bold uppercase text-[#FF5500]">
                {storage?.reachable ? '[STORAGE: ACTIVE]' : '[STORAGE: UNREACHABLE]'}
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs pt-2">
              <div className="p-5 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black shadow-[3px_3px_0px_0px_#000]">
                <span className="text-stone-500 uppercase tracking-widest text-[10px] font-black">
                  VIDEOS BUCKET
                </span>
                <p className="text-2xl font-black text-black dark:text-white mt-1">
                  {storage?.videos_count ?? '—'} files
                </p>
                <p className="text-[11px] text-stone-500 mt-1">
                  {storage?.videos_size_bytes != null ? formatBytes(storage.videos_size_bytes) : '—'}
                </p>
              </div>

              <div className="p-5 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black shadow-[3px_3px_0px_0px_#000]">
                <span className="text-stone-500 uppercase tracking-widest text-[10px] font-black">
                  KEYFRAMES BUCKET
                </span>
                <p className="text-2xl font-black text-black dark:text-white mt-1">
                  {storage?.keyframes_count ?? '—'} frames
                </p>
                <p className="text-[11px] text-stone-500 mt-1">
                  {storage?.keyframes_size_bytes != null ? formatBytes(storage.keyframes_size_bytes) : '—'}
                </p>
              </div>

              <div className="p-5 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black shadow-[3px_3px_0px_0px_#000]">
                <span className="text-stone-500 uppercase tracking-widest text-[10px] font-black">
                  MEDIA BUCKET
                </span>
                <p className="text-2xl font-black text-black dark:text-white mt-1">
                  {storage?.media_bucket || '—'}
                </p>
                <p className="text-[11px] text-[#00D084] font-bold mt-1">
                  {storage?.reachable ? 'CONNECTED' : 'DISCONNECTED'}
                </p>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
