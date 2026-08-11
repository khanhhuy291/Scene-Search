import React, { useState } from 'react'
import {
  Users,
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
  UserX
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
  const [newRole, setNewRole] = useState('user')

  const filteredUsers = usersList.filter((u) => {
    const matchesSearch =
      u.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      u.email.toLowerCase().includes(searchQuery.toLowerCase())
    const matchesRole = roleFilter === 'all' || u.role === roleFilter
    return matchesSearch && matchesRole
  })

  const totalPages = Math.ceil(filteredUsers.length / pageSize) || 1
  const paginatedUsers = filteredUsers.slice(
    (currentPage - 1) * pageSize,
    currentPage * pageSize
  )

  const handleRoleToggle = (user) => {
    toggleUserRole(user.id)
    const newRoleName = user.role === 'admin' ? 'USER' : 'ADMIN'
    addToast(`Updated ${user.name}'s role to ${newRoleName}`, 'info')
  }

  const handleStatusToggle = (user) => {
    toggleUserStatus(user.id)
    const newStatus = user.status === 'active' ? 'SUSPENDED' : 'ACTIVE'
    addToast(`Updated ${user.name}'s account status to ${newStatus}`, 'info')
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
    <div className="space-y-6 animate-fadeIn">
      {/* Table Action Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4 p-5 bg-white dark:bg-[#25211e]/95 rounded-3xl border border-stone-200 dark:border-[#403933] shadow-2xs">
        <div className="relative flex-1 max-w-md">
          <Search className="w-4 h-4 text-stone-400 dark:text-[#847970] absolute left-4 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search users by name or email..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value)
              setCurrentPage(1)
            }}
            className="w-full bg-stone-50 dark:bg-[#181512] text-stone-950 dark:text-[#f3ece4] text-xs font-sans rounded-full pl-10 pr-4 py-2.5 border border-stone-200 dark:border-[#403933] focus:border-stone-950 dark:focus:border-[#789b86] outline-none"
          />
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1 bg-stone-100 dark:bg-[#181512] p-1 rounded-full border border-stone-200 dark:border-[#403933] text-xs font-sans">
            <Filter className="w-3.5 h-3.5 text-stone-500 dark:text-[#a99d92] ml-2" />
            <button
              type="button"
              onClick={() => setRoleFilter('all')}
              className={`px-3 py-1 rounded-full font-bold uppercase text-[10px] tracking-wider transition-all ${
                roleFilter === 'all' ? 'bg-stone-950 dark:bg-[#332e2a] text-white dark:text-[#f3ece4]' : 'text-stone-600 dark:text-[#a99d92] hover:text-stone-950 dark:hover:text-stone-200'
              }`}
            >
              ALL
            </button>
            <button
              type="button"
              onClick={() => setRoleFilter('admin')}
              className={`px-3 py-1 rounded-full font-bold uppercase text-[10px] tracking-wider transition-all ${
                roleFilter === 'admin' ? 'bg-stone-950 dark:bg-[#315c49]/18 text-white dark:text-[#a8c0b0] dark:border dark:border-[#315c49]/45' : 'text-stone-600 dark:text-[#a99d92] hover:text-stone-950 dark:hover:text-stone-200'
              }`}
            >
              ADMINS
            </button>
            <button
              type="button"
              onClick={() => setRoleFilter('user')}
              className={`px-3 py-1 rounded-full font-bold uppercase text-[10px] tracking-wider transition-all ${
                roleFilter === 'user' ? 'bg-stone-950 dark:bg-[#332e2a] text-white dark:text-[#f3ece4]' : 'text-stone-600 dark:text-[#a99d92] hover:text-stone-950 dark:hover:text-stone-200'
              }`}
            >
              USERS
            </button>
          </div>

          <button
            type="button"
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-2 px-5 py-2.5 rounded-full bg-stone-950 dark:bg-[#315c49] hover:bg-orange-700 dark:hover:bg-[#789b86] text-white dark:text-[#f3ece4] font-bold text-xs tracking-widest uppercase transition-all cursor-pointer shrink-0 shadow-sm"
          >
            <UserPlus className="w-3.5 h-3.5" /> ADD USER
          </button>
        </div>
      </div>

      {/* Dense Table */}
      <div className="bg-white dark:bg-[#25211e]/95 rounded-3xl border border-stone-200 dark:border-[#403933] overflow-hidden shadow-2xs">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-stone-50 dark:bg-[#181512] text-stone-500 dark:text-[#a99d92] uppercase tracking-widest font-sans text-[10px] font-bold border-b border-stone-200 dark:border-[#403933]">
                <th className="py-4 px-6">USER DETAILS</th>
                <th className="py-4 px-6">ROLE</th>
                <th className="py-4 px-6">STATUS</th>
                <th className="py-4 px-6">REGISTERED</th>
                <th className="py-4 px-6 text-right">PRIVILEGES & ACTIONS</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100 dark:divide-[#403933]">
              {paginatedUsers.length > 0 ? (
                paginatedUsers.map((u) => (
                  <tr key={u.id} className="hover:bg-stone-50/60 dark:hover:bg-stone-950/40 transition-colors">
                    <td className="py-4 px-6">
                      <div className="flex items-center gap-3">
                        <img
                          src={u.avatar}
                          alt={u.name}
                          className="w-9 h-9 rounded-full object-cover border border-stone-200 dark:border-[#514841] shrink-0"
                        />
                        <div>
                          <div className="font-bold text-stone-950 dark:text-[#f3ece4] text-sm">{u.name}</div>
                          <div className="text-stone-500 dark:text-[#a99d92] font-mono text-[11px]">{u.email}</div>
                        </div>
                      </div>
                    </td>

                    <td className="py-4 px-6">
                      <span
                        className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full font-mono text-[10px] font-bold uppercase tracking-wider ${
                          u.role === 'admin'
                            ? 'bg-orange-50 dark:bg-[#315c49]/12 text-orange-700 dark:text-[#a8c0b0] border border-orange-200 dark:border-[#315c49]/45'
                            : 'bg-stone-100 dark:bg-[#332e2a] text-stone-600 dark:text-[#a99d92] border border-stone-200 dark:border-[#514841]'
                        }`}
                      >
                        {u.role === 'admin' ? <Shield className="w-3 h-3 text-orange-700 dark:text-[#789b86]" /> : <User className="w-3 h-3" />}
                        {u.role}
                      </span>
                    </td>

                    <td className="py-4 px-6">
                      <span
                        className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-mono font-bold uppercase ${
                          u.status === 'active'
                            ? 'bg-emerald-50 dark:bg-[#315c49]/18 text-emerald-700 dark:text-[#789b86] border border-emerald-200 dark:border-[#456f5b]/45'
                            : 'bg-rose-50 dark:bg-[#6b3e3e]/22 text-rose-700 dark:text-[#c98d89] border border-rose-200 dark:border-[#6b3e3e]/50'
                        }`}
                      >
                        {u.status === 'active' ? (
                          <CheckCircle2 className="w-3 h-3 text-emerald-700 dark:text-[#789b86]" />
                        ) : (
                          <AlertTriangle className="w-3 h-3 text-rose-700 dark:text-[#c98d89]" />
                        )}
                        {u.status}
                      </span>
                    </td>

                    <td className="py-4 px-6 font-mono text-stone-500 dark:text-[#a99d92] text-xs">
                      {u.created}
                    </td>

                    <td className="py-4 px-6 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => handleRoleToggle(u)}
                          className="px-3.5 py-1.5 rounded-full bg-stone-100 dark:bg-[#332e2a] hover:bg-stone-950 dark:hover:bg-[#433b35] text-stone-800 dark:text-[#c8bbb0] hover:text-white border border-stone-300 dark:border-[#514841] text-[10px] font-bold tracking-wider uppercase transition-all cursor-pointer flex items-center gap-1"
                        >
                          <ShieldCheck className="w-3.5 h-3.5 text-orange-700 dark:text-[#789b86]" /> TOGGLE ROLE
                        </button>

                        <button
                          type="button"
                          onClick={() => handleStatusToggle(u)}
                          className={`px-3.5 py-1.5 rounded-full border text-[10px] font-bold tracking-wider uppercase transition-all cursor-pointer flex items-center gap-1 ${
                            u.status === 'active'
                              ? 'bg-rose-50 dark:bg-[#3b2424]/60 border-rose-200 dark:border-[#593534] text-rose-700 dark:text-[#c98d89] hover:bg-rose-700 hover:text-white'
                              : 'bg-emerald-50 dark:bg-[#1d352b]/55 border-emerald-200 dark:border-[#294c3e] text-emerald-700 dark:text-[#789b86] hover:bg-emerald-700 hover:text-white'
                          }`}
                        >
                          <UserX className="w-3.5 h-3.5" />
                          {u.status === 'active' ? 'SUSPEND' : 'ACTIVATE'}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5} className="py-8 text-center text-stone-500 dark:text-[#a99d92] text-sm">
                    No users matching filter criteria found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Footer */}
        <div className="p-4 bg-stone-50 dark:bg-[#181512] border-t border-stone-200 dark:border-[#403933] flex items-center justify-between text-xs text-stone-500 dark:text-[#a99d92]">
          <div>
            Showing <span className="font-bold text-stone-950 dark:text-[#f3ece4]">{filteredUsers.length}</span> total system accounts
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={currentPage === 1}
              onClick={() => setCurrentPage(currentPage - 1)}
              className="p-1.5 rounded-full bg-white dark:bg-[#25211e] border border-stone-200 dark:border-[#403933] hover:bg-stone-100 dark:hover:bg-[#38322d] disabled:opacity-40 text-stone-800 dark:text-[#ded3c8] transition-colors cursor-pointer"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="font-mono">
              Page {currentPage} of {totalPages}
            </span>
            <button
              type="button"
              disabled={currentPage === totalPages}
              onClick={() => setCurrentPage(currentPage + 1)}
              className="p-1.5 rounded-full bg-white dark:bg-[#25211e] border border-stone-200 dark:border-[#403933] hover:bg-stone-100 dark:hover:bg-[#38322d] disabled:opacity-40 text-stone-800 dark:text-[#ded3c8] transition-colors cursor-pointer"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Add User Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-stone-950/50 dark:bg-[#181512]/85 backdrop-blur-sm">
          <div className="w-full max-w-md bg-white dark:bg-[#25211e] p-6 sm:p-8 rounded-3xl border border-stone-200 dark:border-[#315c49]/45 shadow-2xl relative space-y-4">
            <h3 className="text-2xl font-serif font-normal text-stone-950 dark:text-[#f3ece4] uppercase tracking-tight">
              ADD NEW USER ACCOUNT
            </h3>
            <form onSubmit={handleAddUser} className="space-y-4">
              <div>
                <label className="block text-[10px] font-sans font-bold uppercase tracking-widest text-stone-500 dark:text-[#a99d92] mb-1">
                  FULL NAME
                </label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="e.g. Maya Lin"
                  className="w-full bg-stone-50 dark:bg-[#181512] text-stone-950 dark:text-[#f3ece4] text-sm rounded-2xl px-4 py-2.5 border border-stone-300 dark:border-[#403933] focus:border-stone-950 dark:focus:border-[#789b86] outline-none"
                  required
                />
              </div>

              <div>
                <label className="block text-[10px] font-sans font-bold uppercase tracking-widest text-stone-500 dark:text-[#a99d92] mb-1">
                  EMAIL ADDRESS
                </label>
                <input
                  type="email"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  placeholder="maya@scenesearch.ai"
                  className="w-full bg-stone-50 dark:bg-[#181512] text-stone-950 dark:text-[#f3ece4] text-sm rounded-2xl px-4 py-2.5 border border-stone-300 dark:border-[#403933] focus:border-stone-950 dark:focus:border-[#789b86] outline-none"
                  required
                />
              </div>

              <div>
                <label className="block text-[10px] font-sans font-bold uppercase tracking-widest text-stone-500 dark:text-[#a99d92] mb-1">
                  PASSWORD
                </label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full bg-stone-50 dark:bg-[#181512] text-stone-950 dark:text-[#f3ece4] text-sm rounded-2xl px-4 py-2.5 border border-stone-300 dark:border-[#403933] focus:border-stone-950 dark:focus:border-[#789b86] outline-none"
                  required
                />
              </div>

              <div>
                <label className="block text-[10px] font-sans font-bold uppercase tracking-widest text-stone-500 dark:text-[#a99d92] mb-1">
                  ROLE
                </label>
                <select
                  value={newRole}
                  onChange={(e) => setNewRole(e.target.value)}
                  className="w-full bg-stone-50 dark:bg-[#181512] text-stone-950 dark:text-[#f3ece4] text-sm rounded-2xl px-4 py-2.5 border border-stone-300 dark:border-[#403933] focus:border-stone-950 dark:focus:border-[#789b86] outline-none"
                >
                  <option value="user">Standard User</option>
                  <option value="admin">Administrator</option>
                </select>
              </div>

              <div className="flex gap-3 pt-4 border-t border-stone-100 dark:border-[#403933]">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="flex-1 py-2.5 rounded-full bg-stone-100 dark:bg-[#332e2a] border border-stone-200 dark:border-[#514841] text-stone-700 dark:text-[#c8bbb0] hover:bg-stone-200 text-xs font-bold uppercase tracking-widest"
                >
                  CANCEL
                </button>
                <button
                  type="submit"
                  className="flex-1 py-2.5 rounded-full bg-stone-950 dark:bg-[#315c49] text-white dark:text-[#f3ece4] hover:bg-orange-700 dark:hover:bg-[#789b86] text-xs font-bold uppercase tracking-widest shadow-sm"
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
