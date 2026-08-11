import React, { useState } from 'react'
import { Sidebar } from '../components/layout/Sidebar'
import { DashboardOverview } from '../components/admin/DashboardOverview'
import { UserManagementTable } from '../components/admin/UserManagementTable'
import { CeleryTaskInspector } from '../components/admin/CeleryTaskInspector'
import { Database, HardDrive } from 'lucide-react'

export const AdminPage = () => {
  const [activeTab, setActiveTab] = useState('overview')
  const [isCollapsed, setIsCollapsed] = useState(false)

  return (
    <div className="flex min-h-[calc(100vh-5rem)] bg-[#F5F0E8] dark:bg-[#181512] transition-colors duration-300">
      {/* Collapsible Admin Sidebar */}
      <Sidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        isCollapsed={isCollapsed}
        setIsCollapsed={setIsCollapsed}
      />

      {/* Main Admin View Content */}
      <main className="flex-1 p-6 md:p-10 max-w-7xl mx-auto overflow-y-auto pb-24">
        {activeTab === 'overview' && <DashboardOverview />}
        {activeTab === 'users' && <UserManagementTable />}
        {activeTab === 'tasks' && <CeleryTaskInspector />}

        {activeTab === 'vectordb' && (
          <div className="bg-white dark:bg-[#25211e]/95 p-8 rounded-3xl border border-stone-200 dark:border-[#403933] shadow-2xs space-y-4 animate-fadeIn">
            <div className="flex items-center gap-3 pl-3 orange-accent-line">
              <h2 className="text-3xl font-serif font-normal text-stone-950 dark:text-[#f3ece4] uppercase tracking-tight">
                Qdrant Collection Schema & Vectors
              </h2>
            </div>
            <p className="text-stone-500 dark:text-[#a99d92] text-xs font-mono">
              Collection: scenes_multimodal_v2 | Vector Size: 512 | Distance: Cosine
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 font-mono text-xs pt-2">
              <div className="p-5 rounded-2xl bg-stone-50 dark:bg-[#181512] border border-stone-200 dark:border-[#403933]">
                <span className="text-stone-500 dark:text-[#a99d92] uppercase tracking-widest text-[10px] font-bold">TOTAL INDEX POINTS</span>
                <p className="text-3xl font-serif text-stone-950 dark:text-[#789b86] mt-1">84,920</p>
              </div>
              <div className="p-5 rounded-2xl bg-stone-50 dark:bg-[#181512] border border-stone-200 dark:border-[#403933]">
                <span className="text-stone-500 dark:text-[#a99d92] uppercase tracking-widest text-[10px] font-bold">HNSW M PARAMETER</span>
                <p className="text-3xl font-serif text-stone-950 dark:text-[#789b86] mt-1">M=16</p>
              </div>
              <div className="p-5 rounded-2xl bg-stone-50 dark:bg-[#181512] border border-stone-200 dark:border-[#403933]">
                <span className="text-stone-500 dark:text-[#a99d92] uppercase tracking-widest text-[10px] font-bold">EF_CONSTRUCT</span>
                <p className="text-3xl font-serif text-stone-950 dark:text-[#789b86] mt-1">100</p>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'storage' && (
          <div className="bg-white dark:bg-[#25211e]/95 p-8 rounded-3xl border border-stone-200 dark:border-[#403933] shadow-2xs space-y-4 animate-fadeIn">
            <div className="flex items-center gap-3 pl-3 orange-accent-line">
              <h2 className="text-3xl font-serif font-normal text-stone-950 dark:text-[#f3ece4] uppercase tracking-tight">
                RAID 0 Storage Volume Diagnostics
              </h2>
            </div>
            <p className="text-stone-500 dark:text-[#a99d92] text-xs font-mono">
              Path: /var/data/scenesearch/media | Used: 2.48 TB / 3.6 TB
            </p>
            <div className="w-full bg-stone-100 dark:bg-[#181512] h-4 rounded-full overflow-hidden p-0.5 border border-stone-200 dark:border-[#403933]">
              <div className="bg-orange-700 dark:bg-[#294c3e] h-full rounded-full w-[68%]" />
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
