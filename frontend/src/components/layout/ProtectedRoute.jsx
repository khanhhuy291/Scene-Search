import React from 'react'
import { Navigate, useLocation, Link } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { ShieldAlert, Terminal } from 'lucide-react'

/**
 * Gate a route by authentication and optional role allow-list.
 */
export const ProtectedRoute = ({ children, roles, requireAdmin = false }) => {
  const { user, isAuthenticated, homePath, isLoading } = useAuth()
  const location = useLocation()

  const allowedRoles = requireAdmin ? ['admin'] : roles

  if (isLoading) {
    return (
      <div className="min-h-[70vh] flex items-center justify-center bg-[#F7F4EE] dark:bg-[#141210]">
        <div className="flex flex-col items-center gap-3 p-6 bg-white dark:bg-[#1C1A17] border-2 border-black shadow-[4px_4px_0px_0px_#000]">
          <div className="w-8 h-8 bg-black text-white flex items-center justify-center font-mono font-black animate-spin">
            S
          </div>
          <p className="text-black dark:text-white text-xs font-mono font-black uppercase tracking-widest">
            INITIALIZING SECURITY CONTEXT...
          </p>
        </div>
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/auth" state={{ from: location }} replace />
  }

  if (allowedRoles && allowedRoles.length > 0 && !allowedRoles.includes(user?.role)) {
    return (
      <div className="min-h-[70vh] flex items-center justify-center p-6 bg-[#F7F4EE] dark:bg-[#141210]">
        <div className="max-w-md w-full bg-white dark:bg-[#1C1A17] p-8 border-3 border-black shadow-[8px_8px_0px_0px_#000] text-center space-y-4 font-mono">
          <div className="w-14 h-14 bg-red-100 border-2 border-red-600 flex items-center justify-center mx-auto text-red-600 shadow-[2px_2px_0px_0px_#000]">
            <ShieldAlert className="w-7 h-7" />
          </div>
          <h2 className="text-2xl font-black uppercase tracking-tight text-black dark:text-white">
            ACCESS RESTRICTED
          </h2>
          <p className="text-stone-700 dark:text-stone-300 text-xs font-sans leading-relaxed">
            This module requires role:{' '}
            <span className="font-mono font-bold text-red-600 bg-red-50 border border-red-200 px-1 py-0.5">
              {allowedRoles.join(' / ').toUpperCase()}
            </span>
            . Your account (<span className="font-bold text-black dark:text-white">{user?.email}</span>) is signed in as <span className="font-mono font-black uppercase underline">{user?.role}</span>.
          </p>
          <div className="pt-2">
            <Link
              to={homePath}
              className="inline-flex items-center gap-1.5 px-6 py-2.5 bg-black hover:bg-[#FF5500] text-white hover:text-black text-xs font-black uppercase tracking-widest border-2 border-black shadow-[3px_3px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all"
            >
              <Terminal className="w-3.5 h-3.5" />
              <span>RETURN TO WORKSPACE</span>
            </Link>
          </div>
        </div>
      </div>
    )
  }

  return children
}
