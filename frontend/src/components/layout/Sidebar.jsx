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
  Infinity as InfinityIcon,
  Activity
} from 'lucide-react'

export const Sidebar = ({ activeTab, setActiveTab, isCollapsed, setIsCollapsed }) => {
  const menuItems = [
    { id: 'overview', label: 'Overview', icon: LayoutDashboard },
    { id: 'users', label: 'Users', icon: Users, badge: '4' },
    { id: 'tasks', label: 'Celery Workers', icon: Cpu, badge: '12 Active' },
    { id: 'vectordb', label: 'Qdrant Vector', icon: Database },
    { id: 'storage', label: 'Storage & Logs', icon: HardDrive }
  ]

  return (
    <aside
      className={`h-[calc(100vh-5rem)] sticky top-20 bg-[#F5F0E8] dark:bg-[#0c121e]/90 border-r border-stone-200 dark:border-[#403933]/80 flex flex-col justify-between transition-all duration-300 z-30 select-none ${
        isCollapsed ? 'w-20' : 'w-64'
      }`}
    >
      {/* Upper Navigation section */}
      <div className="p-3">
        {/* Toggle Button Header */}
        <div className="flex items-center justify-between px-2 py-3 mb-2 border-b border-stone-200 dark:border-[#403933]/80">
          {!isCollapsed && (
            <div className="flex items-center gap-2 text-xs font-bold font-sans tracking-widest text-stone-950 dark:text-[#789b86] uppercase font-mono">
              <Shield className="w-4 h-4 text-orange-700 dark:text-[#789b86]" />
              <span>ADMIN CONSOLE</span>
            </div>
          )}
          <button
            type="button"
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="p-1.5 rounded-full bg-white dark:bg-[#25211e] border border-stone-300 dark:border-[#403933] hover:bg-stone-100 dark:hover:bg-[#38322d] text-stone-700 dark:text-[#a99d92] transition-colors mx-auto cursor-pointer"
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
                className={`w-full flex items-center gap-3 px-3.5 py-3 rounded-full text-xs font-bold tracking-widest uppercase transition-all cursor-pointer ${
                  isActive
                    ? 'bg-stone-950 text-white dark:bg-[#294c3e] dark:text-[#a8c0b0] dark:border dark:border-[#315c49]/45 shadow-sm'
                    : 'text-stone-600 dark:text-[#a99d92] hover:text-stone-950 dark:hover:text-stone-200 hover:bg-stone-200/60 dark:hover:bg-[#2d2824]/80'
                }`}
              >
                <Icon className={`w-4 h-4 shrink-0 ${isActive ? 'text-orange-400 dark:text-[#789b86]' : 'text-stone-500 dark:text-[#a99d92]'}`} />
                {!isCollapsed && (
                  <div className="flex-1 flex items-center justify-between overflow-hidden gap-1.5">
                    <span className="truncate">{item.label}</span>
                    {item.badge && (
                      <span
                        className={`text-[9px] font-mono px-2 py-0.5 rounded-full shrink-0 whitespace-nowrap ${
                          isActive
                            ? 'bg-orange-700 dark:bg-[#789b86] text-white dark:text-[#f3ece4] font-bold'
                            : 'bg-stone-200 dark:bg-[#332e2a] text-stone-700 dark:text-[#a99d92] font-bold'
                        }`}
                      >
                        {item.badge}
                      </span>
                    )}
                  </div>
                )}
              </button>
            )
          })}
        </nav>
      </div>

      {/* Bottom Live System Indicator */}
      <div className="p-3 border-t border-stone-200 dark:border-[#403933]/80">
        {!isCollapsed ? (
          <div className="p-3.5 rounded-2xl bg-white dark:bg-[#25211e]/85 border border-stone-200 dark:border-[#403933] text-xs shadow-2xs space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-stone-500 dark:text-[#a99d92] font-sans text-[9px] font-bold uppercase tracking-widest">CLUSTER GPU</span>
              <span className="text-orange-700 dark:text-[#789b86] font-bold font-mono text-[11px]">NVIDIA RTX 4090</span>
            </div>
            <div className="w-full bg-stone-100 dark:bg-[#332e2a] h-1.5 rounded-full overflow-hidden border border-stone-200 dark:border-[#514841]">
              <div className="bg-orange-700 dark:bg-[#789b86] h-full w-[42%]" />
            </div>
            <div className="flex justify-between text-[10px] font-mono text-stone-500 dark:text-[#a99d92]">
              <span>LOAD: 42%</span>
              <span>TEMP: 58°C</span>
            </div>
          </div>
        ) : (
          <div className="flex justify-center py-2" title="Cluster Active">
            <Activity className="w-5 h-5 text-orange-700 dark:text-[#789b86] animate-pulse" />
          </div>
        )}
      </div>
    </aside>
  )
}
