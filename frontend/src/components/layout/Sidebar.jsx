import React from 'react'
import {
  LayoutDashboard,
  Users,
  Cpu,
  Database,
  HardDrive,
  ChevronLeft,
  ChevronRight,
  Shield,
  Activity,
  Sparkles,
  Flame,
  BarChart3
} from 'lucide-react'

export const Sidebar = ({ activeTab, setActiveTab, isCollapsed, setIsCollapsed }) => {
  const menuItems = [
    { id: 'traces', label: 'Truy vết (APM Traces)', icon: Flame },
    { id: 'eval', label: 'Đánh giá & Benchmark', icon: BarChart3 },
    { id: 'overview', label: 'Tổng quan Hệ thống', icon: LayoutDashboard },
    { id: 'corpus', label: 'Sức khỏe Dữ liệu', icon: Activity },
    { id: 'rlhf', label: 'RLHF & Reranker', icon: Sparkles },
    { id: 'tasks', label: 'Celery Workers', icon: Cpu },
    { id: 'users', label: 'Quản lý Người dùng', icon: Users },
    { id: 'vectordb', label: 'Vector Qdrant', icon: Database },
    { id: 'storage', label: 'Lưu trữ Object Storage', icon: HardDrive }
  ]

  return (
    <aside
      className={`h-[calc(100vh-4.5rem)] sticky top-18 bg-[#F7F4EE] dark:bg-[#141210] border-r-2 border-black flex flex-col justify-between transition-all duration-200 z-30 select-none font-mono ${
        isCollapsed ? 'w-20' : 'w-64'
      }`}
    >
      {/* Upper Navigation section */}
      <div className="p-3">
        {/* Toggle Button Header */}
        <div className="flex items-center justify-between px-2 py-3 mb-2 border-b-2 border-black">
          {!isCollapsed && (
            <div className="flex items-center gap-2 text-xs font-black uppercase text-black dark:text-white">
              <Shield className="w-4 h-4 text-[#FF5500]" />
              <span>ADMIN CONSOLE</span>
            </div>
          )}
          <button
            type="button"
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="p-1.5 bg-white dark:bg-stone-900 border border-black hover:bg-[#FF5500] hover:text-black text-black dark:text-white transition-colors mx-auto cursor-pointer shadow-[1.5px_1.5px_0px_0px_#000]"
            title={isCollapsed ? 'Expand Sidebar' : 'Collapse Sidebar'}
          >
            {isCollapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
          </button>
        </div>

        {/* Navigation list */}
        <nav className="space-y-1.5">
          {menuItems.map((item) => {
            const Icon = item.icon
            const isActive = activeTab === item.id

            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setActiveTab(item.id)}
                className={`w-full flex items-center gap-3 px-3.5 py-2.5 text-xs font-black uppercase transition-all cursor-pointer border-2 ${
                  isActive
                    ? 'bg-black text-white border-black shadow-[2px_2px_0px_0px_#FF5500]'
                    : 'bg-transparent text-stone-800 dark:text-stone-300 border-transparent hover:border-black hover:bg-white dark:hover:bg-stone-900 hover:text-black dark:hover:text-white'
                }`}
              >
                <Icon className={`w-4 h-4 shrink-0 ${isActive ? 'text-[#FF5500]' : 'text-stone-500'}`} />
                {!isCollapsed && <span className="truncate">{item.label}</span>}
              </button>
            )
          })}
        </nav>
      </div>

      <div className="p-3 border-t-2 border-black">
        {!isCollapsed ? (
          <p className="px-2 text-[10px] font-mono text-stone-600 dark:text-stone-400 leading-relaxed">
            Telemetry from <span className="font-bold text-black dark:text-white">GET /api/v1/admin/telemetry</span>.
          </p>
        ) : (
          <div className="flex justify-center py-2" title="Live telemetry">
            <Activity className="w-5 h-5 text-[#FF5500]" />
          </div>
        )}
      </div>
    </aside>
  )
}
