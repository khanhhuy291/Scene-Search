import React, { useState } from 'react'
import {
  Search,
  Shield,
  User,
  UserPlus,
  Filter,
  CheckCircle2,
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
  UserX,
  X
} from 'lucide-react'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'

export const UserManagementTable = () => {
  const { usersList, toggleUserRole, toggleUserStatus, register } = useAuth()
  const { addToast } = useToast()

  const [searchQuery, setSearchQuery] = useState('')
  const [roleFilter, setRoleFilter] = useState('all')
  const [currentPage, setCurrentPage] = useState(1)
  const pageSize = 5

  const [showAddModal, setShowAddModal] = useState(false)
  const [newName, setNewName] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newRole, setNewRole] = useState('engineer')

  const filteredUsers = (usersList || []).filter((u) => {
    const name = u.display_name || u.name || ''
    const email = u.email || ''
    const matchesSearch =
      name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      email.toLowerCase().includes(searchQuery.toLowerCase())
    const matchesRole = roleFilter === 'all' || u.role === roleFilter
    return matchesSearch && matchesRole
  })

  const totalPages = Math.ceil(filteredUsers.length / pageSize) || 1
  const paginatedUsers = filteredUsers.slice(
    (currentPage - 1) * pageSize,
    currentPage * pageSize
  )

  const handleRoleToggle = async (user) => {
    const roleCycle = {
      engineer: 'admin',
      admin: 'engineer'
    }
    const nextRole = roleCycle[user.role] || 'engineer'
    try {
      await toggleUserRole(user.id, nextRole)
      addToast(`Updated ${(user.display_name || user.email)} role to ${nextRole.toUpperCase()}`, 'info')
    } catch (err) {
      addToast(err.message || 'Failed to update role', 'error')
    }
  }

  const handleStatusToggle = async (user) => {
    const nextStatus = !user.is_active
    try {
      await toggleUserStatus(user.id, nextStatus)
      addToast(`Updated ${(user.display_name || user.email)} status to ${nextStatus ? 'ACTIVE' : 'SUSPENDED'}`, 'info')
    } catch (err) {
      addToast(err.message || 'Failed to update status', 'error')
    }
  }

  const handleAddUser = async (e) => {
    e.preventDefault()
    if (!newName || !newEmail || !newPassword) {
      addToast('Please fill out all user details', 'error')
      return
    }

    try {
      await register(newName, newEmail, newPassword, newRole)
      addToast(`User ${newName} created successfully!`, 'success')
      setShowAddModal(false)
      setNewName('')
      setNewEmail('')
      setNewPassword('')
    } catch (err) {
      addToast(err.message || 'Failed to create user', 'error')
    }
  }

  return (
    <div className="space-y-6 font-mono animate-fadeIn">
      {/* Table Action Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4 p-5 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000]">
        <div className="relative flex-1 max-w-md">
          <Search className="w-4 h-4 text-black absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="FILTER ACCOUNTS BY NAME / EMAIL..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value)
              setCurrentPage(1)
            }}
            className="w-full bg-[#F7F4EE] dark:bg-stone-900 text-black dark:text-white text-xs font-bold pl-10 pr-4 py-2.5 border-2 border-black shadow-[2px_2px_0px_0px_#000] uppercase outline-none"
          />
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-1 bg-[#F7F4EE] dark:bg-stone-900 p-1 border-2 border-black text-xs">
            <Filter className="w-3.5 h-3.5 text-stone-500 ml-1" />
            <button
              type="button"
              onClick={() => setRoleFilter('all')}
              className={`px-3 py-1 font-black uppercase text-[10px] tracking-wider transition-all cursor-pointer ${
                roleFilter === 'all'
                  ? 'bg-black text-white'
                  : 'text-stone-700 dark:text-stone-300 hover:text-black'
              }`}
            >
              ALL
            </button>
            <button
              type="button"
              onClick={() => setRoleFilter('admin')}
              className={`px-3 py-1 font-black uppercase text-[10px] tracking-wider transition-all cursor-pointer ${
                roleFilter === 'admin'
                  ? 'bg-black text-[#FF5500]'
                  : 'text-stone-700 dark:text-stone-300 hover:text-black'
              }`}
            >
              ADMINS
            </button>
            <button
              type="button"
              onClick={() => setRoleFilter('engineer')}
              className={`px-3 py-1 font-black uppercase text-[10px] tracking-wider transition-all cursor-pointer ${
                roleFilter === 'engineer'
                  ? 'bg-black text-[#00D084]'
                  : 'text-stone-700 dark:text-stone-300 hover:text-black'
              }`}
            >
              ENGINEERS
            </button>
          </div>

          <button
            type="button"
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-2 px-5 py-2.5 bg-black hover:bg-[#FF5500] text-white hover:text-black font-black text-xs tracking-wider uppercase border-2 border-black shadow-[3px_3px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all cursor-pointer shrink-0"
          >
            <UserPlus className="w-3.5 h-3.5" /> ADD USER
          </button>
        </div>
      </div>

      {/* Dense Brutalist Table */}
      <div className="bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-[#F7F4EE] dark:bg-stone-900 text-black dark:text-white uppercase tracking-wider text-[11px] font-black border-b-2 border-black">
                <th className="py-3.5 px-6">USER DETAILS</th>
                <th className="py-3.5 px-6">ROLE</th>
                <th className="py-3.5 px-6">STATUS</th>
                <th className="py-3.5 px-6">REGISTERED</th>
                <th className="py-3.5 px-6 text-right">PRIVILEGES & ACTIONS</th>
              </tr>
            </thead>
            <tbody className="divide-y-2 divide-black/10">
              {paginatedUsers.length > 0 ? (
                paginatedUsers.map((u) => {
                  const displayName = u.display_name || u.name || 'Anonymous User'
                  const avatarUrl = u.avatar || `https://api.dicebear.com/7.x/bottts/svg?seed=${u.email}`
                  const isActive = u.is_active !== undefined ? u.is_active : u.status === 'active'
                  const createdDate = u.created_at ? new Date(u.created_at).toLocaleDateString() : (u.created || 'N/A')

                  return (
                    <tr key={u.id} className="hover:bg-[#F7F4EE] dark:hover:bg-stone-900 transition-colors">
                      <td className="py-4 px-6">
                        <div className="flex items-center gap-3">
                          <img
                            src={avatarUrl}
                            alt={displayName}
                            className="w-9 h-9 border border-black shrink-0 bg-stone-100"
                          />
                          <div>
                            <div className="font-black text-black dark:text-white text-sm">{displayName}</div>
                            <div className="text-stone-500 font-mono text-[11px]">{u.email}</div>
                          </div>
                        </div>
                      </td>

                      <td className="py-4 px-6">
                        <span
                          className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 text-[10px] font-black uppercase border ${
                            u.role === 'admin'
                              ? 'bg-[#FF5500] text-black border-black shadow-[1px_1px_0px_0px_#000]'
                              : 'bg-white dark:bg-stone-800 text-black dark:text-white border-black'
                          }`}
                        >
                          {u.role === 'admin' ? <Shield className="w-3 h-3" /> : <User className="w-3 h-3" />}
                          {u.role}
                        </span>
                      </td>

                      <td className="py-4 px-6">
                        <span
                          className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 text-[10px] font-black uppercase border ${
                            isActive
                              ? 'bg-[#00D084] text-black border-black shadow-[1px_1px_0px_0px_#000]'
                              : 'bg-red-100 text-red-900 border-red-600'
                          }`}
                        >
                          {isActive ? (
                            <CheckCircle2 className="w-3 h-3" />
                          ) : (
                            <AlertTriangle className="w-3 h-3" />
                          )}
                          {isActive ? 'ACTIVE' : 'SUSPENDED'}
                        </span>
                      </td>

                      <td className="py-4 px-6 font-bold text-stone-600 dark:text-stone-400 text-xs">
                        {createdDate}
                      </td>

                      <td className="py-4 px-6 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            type="button"
                            onClick={() => handleRoleToggle(u)}
                            className="px-3 py-1.5 bg-[#F7F4EE] hover:bg-black hover:text-white text-black text-[10px] font-black uppercase border border-black shadow-[2px_2px_0px_0px_#000] transition-all cursor-pointer flex items-center gap-1"
                          >
                            <ShieldCheck className="w-3.5 h-3.5 text-[#FF5500]" /> CHANGE ROLE
                          </button>

                          <button
                            type="button"
                            onClick={() => handleStatusToggle(u)}
                            className={`px-3 py-1.5 border text-[10px] font-black uppercase transition-all cursor-pointer flex items-center gap-1 shadow-[2px_2px_0px_0px_#000] ${
                              isActive
                                ? 'bg-red-100 border-red-600 text-red-900 hover:bg-red-600 hover:text-white'
                                : 'bg-[#00D084] border-black text-black hover:bg-black hover:text-white'
                            }`}
                          >
                            <UserX className="w-3.5 h-3.5" />
                            {isActive ? 'SUSPEND' : 'ACTIVATE'}
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })
              ) : (
                <tr>
                  <td colSpan={5} className="py-8 text-center text-stone-500 text-sm">
                    [NO USERS MATCHING FILTER CRITERIA]
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Footer */}
        <div className="p-4 bg-[#F7F4EE] dark:bg-stone-900 border-t-2 border-black flex items-center justify-between text-xs text-stone-600 dark:text-stone-400">
          <div>
            SHOWING <span className="font-black text-black dark:text-white">{filteredUsers.length}</span> TOTAL SYSTEM ACCOUNTS
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={currentPage === 1}
              onClick={() => setCurrentPage(currentPage - 1)}
              className="p-1.5 bg-white dark:bg-stone-800 border border-black hover:bg-black hover:text-white disabled:opacity-30 text-black dark:text-white transition-colors cursor-pointer shadow-[1px_1px_0px_0px_#000]"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="font-bold">
              PAGE {currentPage} OF {totalPages}
            </span>
            <button
              type="button"
              disabled={currentPage === totalPages}
              onClick={() => setCurrentPage(currentPage + 1)}
              className="p-1.5 bg-white dark:bg-stone-800 border border-black hover:bg-black hover:text-white disabled:opacity-30 text-black dark:text-white transition-colors cursor-pointer shadow-[1px_1px_0px_0px_#000]"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Add User Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
          <div className="w-full max-w-md bg-[#F7F4EE] dark:bg-[#1C1A17] p-6 sm:p-8 border-3 border-black shadow-[10px_10px_0px_0px_#000] relative space-y-4">
            <div className="flex items-center justify-between pb-3 border-b-2 border-black">
              <h3 className="text-xl font-black text-black dark:text-white uppercase tracking-tight">
                PROVISION NEW ACCOUNT
              </h3>
              <button
                type="button"
                onClick={() => setShowAddModal(false)}
                className="p-1 hover:bg-black hover:text-white transition-colors cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleAddUser} className="space-y-4">
              <div>
                <label className="block text-[11px] font-black uppercase tracking-wider text-stone-600 dark:text-stone-400 mb-1">
                  FULL NAME:
                </label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="e.g. Alex Rivera"
                  className="w-full bg-white dark:bg-stone-800 text-black dark:text-white text-xs font-bold px-3 py-2.5 border-2 border-black shadow-[2px_2px_0px_0px_#000] outline-none"
                  required
                />
              </div>

              <div>
                <label className="block text-[11px] font-black uppercase tracking-wider text-stone-600 dark:text-stone-400 mb-1">
                  EMAIL ADDRESS:
                </label>
                <input
                  type="email"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  placeholder="alex@scenesearch.ai"
                  className="w-full bg-white dark:bg-stone-800 text-black dark:text-white text-xs font-bold px-3 py-2.5 border-2 border-black shadow-[2px_2px_0px_0px_#000] outline-none"
                  required
                />
              </div>

              <div>
                <label className="block text-[11px] font-black uppercase tracking-wider text-stone-600 dark:text-stone-400 mb-1">
                  PASSWORD (MIN 8 CHARS):
                </label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full bg-white dark:bg-stone-800 text-black dark:text-white text-xs font-bold px-3 py-2.5 border-2 border-black shadow-[2px_2px_0px_0px_#000] outline-none"
                  required
                />
              </div>

              <div>
                <label className="block text-[11px] font-black uppercase tracking-wider text-stone-600 dark:text-stone-400 mb-1">
                  ACCESS ROLE:
                </label>
                <select
                  value={newRole}
                  onChange={(e) => setNewRole(e.target.value)}
                  className="w-full bg-white dark:bg-stone-800 text-black dark:text-white text-xs font-bold px-3 py-2.5 border-2 border-black shadow-[2px_2px_0px_0px_#000] outline-none uppercase"
                >
                  <option value="engineer">ENGINEER (Search & Annotation)</option>
                  <option value="admin">ADMINISTRATOR (Full Privileges)</option>
                </select>
              </div>

              <div className="flex gap-3 pt-3 border-t-2 border-black">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="flex-1 py-2.5 bg-white hover:bg-stone-200 text-black text-xs font-black uppercase border-2 border-black shadow-[2px_2px_0px_0px_#000] cursor-pointer"
                >
                  CANCEL
                </button>
                <button
                  type="submit"
                  className="flex-1 py-2.5 bg-black hover:bg-[#FF5500] text-white hover:text-black text-xs font-black uppercase border-2 border-black shadow-[2px_2px_0px_0px_#FF5500] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all cursor-pointer"
                >
                  SAVE USER
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
