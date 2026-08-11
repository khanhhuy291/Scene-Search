import React from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { ShieldAlert, Infinity as InfinityIcon } from 'lucide-react'

export const ProtectedRoute = ({ children, requireAdmin = false }) => {
  const { user, isAuthenticated, isAdmin, isLoading } = useAuth()
  const location = useLocation()

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#F5F0E8]">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 rounded-full bg-white border border-stone-200 flex items-center justify-center text-orange-700 shadow-xs animate-pulse">
            <InfinityIcon className="w-6 h-6 stroke-[2.2]" />
          </div>
          <p className="text-stone-500 text-xs font-mono uppercase tracking-widest">INITIALIZING SECURITY CONTEXT...</p>
        </div>
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/auth" state={{ from: location }} replace />
  }

  if (requireAdmin && !isAdmin) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6 bg-[#F5F0E8]">
        <div className="max-w-md w-full bg-white p-8 rounded-3xl border border-stone-200 text-center relative overflow-hidden shadow-sm space-y-4">
          <div className="w-16 h-16 rounded-full bg-rose-50 border border-rose-200 flex items-center justify-center mx-auto text-rose-700">
            <ShieldAlert className="w-8 h-8" />
          </div>
          <h2 className="text-3xl font-serif text-stone-950 font-normal uppercase tracking-tighter">ACCESS RESTRICTED</h2>
          <p className="text-stone-600 text-xs font-sans leading-relaxed">
            The Admin Management Dashboard requires elevated privileges (<code className="text-rose-700 font-mono font-bold">role: admin</code>).
            Your current account (<span className="text-stone-950 font-bold">{user?.email}</span>) is signed in as a standard user.
          </p>
          <div className="pt-2">
            <a
              href="/search"
              className="inline-flex items-center px-6 py-2.5 rounded-full bg-stone-950 hover:bg-orange-700 text-white text-xs font-bold uppercase tracking-widest transition-all shadow-sm"
            >
              RETURN TO SEARCH
            </a>
          </div>
        </div>
      </div>
    )
  }

  return children
}
