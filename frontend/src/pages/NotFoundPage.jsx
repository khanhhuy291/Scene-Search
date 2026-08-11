import React from 'react'
import { Link } from 'react-router-dom'
import { Film, Home } from 'lucide-react'

export const NotFoundPage = () => {
  return (
    <div className="min-h-[calc(100vh-5rem)] flex items-center justify-center p-6 text-center bg-[#F5F0E8] dark:bg-[#181512] transition-colors duration-300">
      <div className="max-w-md bg-white dark:bg-[#25211e]/95 p-8 rounded-3xl border border-stone-200 dark:border-[#403933] space-y-6 shadow-xl">
        <div className="w-16 h-16 rounded-full bg-stone-100 dark:bg-[#315c49]/12 border border-stone-200 dark:border-[#315c49]/35 text-orange-700 dark:text-[#789b86] flex items-center justify-center mx-auto">
          <Film className="w-8 h-8" />
        </div>

        <div>
          <h1 className="text-5xl font-serif font-normal text-stone-950 dark:text-[#f3ece4] tracking-tight">404</h1>
          <h2 className="text-lg font-bold text-stone-900 dark:text-[#ded3c8] mt-1 uppercase tracking-wider">Scene Not Found</h2>
          <p className="text-stone-500 dark:text-[#a99d92] text-xs mt-2 font-sans">
            The requested vector page or resource route does not exist in the SceneSearch index.
          </p>
        </div>

        <Link
          to="/search"
          className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-full bg-stone-950 dark:bg-[#315c49] text-white dark:text-[#f3ece4] font-bold text-xs hover:bg-orange-700 dark:hover:bg-[#789b86] transition-all uppercase tracking-widest shadow-md"
        >
          <Home className="w-4 h-4" /> Return to Semantic Search
        </Link>
      </div>
    </div>
  )
}
