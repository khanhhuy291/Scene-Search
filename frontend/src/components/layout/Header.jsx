import React, { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  Search,
  Upload,
  LayoutDashboard,
  LogOut,
  User,
  Shield,
  Menu,
  X,
  Sun,
  Moon
} from 'lucide-react'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useTheme } from '../../context/ThemeContext'

export const Header = () => {
  const { user, isAuthenticated, isAdmin, logout } = useAuth()
  const { addToast } = useToast()
  const { theme, toggleTheme, isDark } = useTheme()
  const location = useLocation()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [userDropdownOpen, setUserDropdownOpen] = useState(false)

  const handleLogout = () => {
    logout()
    addToast('Signed out successfully', 'info')
    setUserDropdownOpen(false)
  }

  const handleToggleTheme = () => {
    toggleTheme()
    const nextMode = isDark ? 'Light Mode (Classic AI Lab)' : 'Dark Mode (Warm Editorial)'
    addToast(`Switched to ${nextMode}`, 'info')
  }

  const navLinks = [
    { name: 'SEARCH', path: '/search', icon: Search },
    { name: 'INGEST', path: '/ingest', icon: Upload },
    ...(isAdmin ? [{ name: 'ADMIN DASHBOARD', path: '/admin', icon: LayoutDashboard }] : [])
  ]

  return (
    <header className="sticky top-0 z-40 w-full border-b border-stone-200 dark:border-[#403933] bg-[#F5F0E8]/90 dark:bg-[#181512]/90 backdrop-blur-md transition-colors duration-300">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-20 flex items-center justify-between">
        {/* Brand logo */}
        <div className="flex items-center gap-8">
          <Link to="/" className="flex items-center gap-3 group">
            <img
              src="/brand/logo-primary.jpg"
              alt="SceneSearch logo"
              className="w-12 h-12 rounded-full object-cover drop-shadow-md group-hover:scale-105 transition-transform duration-300"
            />
            <div className="flex flex-col">
              <span className="font-serif font-normal text-xl tracking-tighter text-stone-950 dark:text-[#f3ece4] uppercase leading-none">
                SCENESEARCH
              </span>
              <span className="text-[9px] font-sans font-semibold tracking-widest text-stone-500 dark:text-[#789b86] uppercase mt-1">
                MULTIMODAL AI LAB v2.4
              </span>
            </div>
          </Link>

          {/* Desktop Nav Links */}
          <nav className="hidden md:flex items-center gap-2">
            {navLinks.map((link) => {
              const Icon = link.icon
              const isActive = location.pathname === link.path
              return (
                <Link
                  key={link.path}
                  to={link.path}
                  className={`flex items-center gap-2 px-4 py-2 rounded-full text-xs font-sans font-semibold tracking-widest transition-all ${
                    isActive
                      ? 'bg-stone-950 text-white dark:bg-[#315c49]/12 dark:text-[#a8c0b0] dark:border dark:border-[#315c49]/35 shadow-sm'
                      : 'text-stone-600 dark:text-[#a99d92] hover:text-stone-950 dark:hover:text-stone-200 hover:bg-stone-200/60 dark:hover:bg-[#332e2a]/80'
                  }`}
                >
                  <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-orange-300 dark:text-[#789b86]' : 'text-stone-500 dark:text-[#a99d92]'}`} />
                  {link.name}
                </Link>
              )
            })}
          </nav>
        </div>

        {/* Right side status, theme toggle & User menu */}
        <div className="flex items-center gap-3 sm:gap-4">
          {/* Status Badge */}
          <div className="hidden lg:flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-stone-200/70 dark:bg-[#315c49]/18 border border-stone-300 dark:border-[#456f5b]/45 text-stone-700 dark:text-[#789b86] text-[11px] font-mono">
            <span className="w-2 h-2 rounded-full bg-orange-600 dark:bg-[#789b86] animate-pulse" />
            <span>{isDark ? 'QDRANT VECTOR CLUSTER ACTIVE' : 'QDRANT CLUSTER ONLINE'}</span>
          </div>

          {/* Theme Toggle Button (Light ↔ Dark) */}
          <button
            type="button"
            onClick={handleToggleTheme}
            className="p-2.5 rounded-full bg-white dark:bg-[#25211e] border border-stone-300 dark:border-[#403933] text-stone-700 dark:text-[#ded3c8] hover:border-orange-700 dark:hover:border-[#789b86] transition-all cursor-pointer shadow-xs flex items-center justify-center"
            title={`Switch to ${isDark ? 'Light' : 'Dark'} Mode`}
            aria-label="Toggle Theme Mode"
          >
            {isDark ? (
              <Sun className="w-4 h-4 text-amber-400 hover:rotate-45 transition-transform" />
            ) : (
              <Moon className="w-4 h-4 text-orange-700 hover:-rotate-12 transition-transform" />
            )}
          </button>

          {isAuthenticated ? (
            <div className="relative">
              <button
                type="button"
                onClick={() => setUserDropdownOpen(!userDropdownOpen)}
                className="flex items-center gap-3 p-1.5 pl-2.5 rounded-full border border-stone-300 dark:border-[#403933] hover:border-stone-400 dark:hover:border-stone-700 bg-white dark:bg-[#25211e] transition-all cursor-pointer shadow-xs"
              >
                <div className="flex flex-col text-right">
                  <span className="text-xs font-bold text-stone-950 dark:text-[#ded3c8] leading-none">
                    {user.name}
                  </span>
                  <span className="text-[9px] font-mono tracking-wider text-orange-700 dark:text-[#789b86] uppercase mt-0.5">
                    {user.role}
                  </span>
                </div>
                <img
                  src={user.avatar}
                  alt={user.name}
                  className="w-8 h-8 rounded-full object-cover border border-stone-200 dark:border-[#315c49]/45"
                />
              </button>

              {/* User Dropdown */}
              {userDropdownOpen && (
                <div className="absolute right-0 mt-2 w-60 bg-white dark:bg-[#25211e] rounded-2xl border border-stone-200 dark:border-[#403933] shadow-xl py-2 z-50 animate-fadeIn">
                  <div className="px-4 py-3 border-b border-stone-100 dark:border-[#403933]">
                    <p className="text-xs font-bold text-stone-950 dark:text-[#ded3c8]">{user.name}</p>
                    <p className="text-[11px] text-stone-500 dark:text-[#a99d92] truncate">{user.email}</p>
                    <span className="inline-flex items-center gap-1 mt-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-widest bg-stone-100 dark:bg-[#315c49]/12 text-orange-700 dark:text-[#a8c0b0] border border-stone-200 dark:border-[#315c49]/35">
                      {user.role === 'admin' ? <Shield className="w-3 h-3 text-orange-700 dark:text-[#789b86]" /> : <User className="w-3 h-3 text-stone-600 dark:text-[#a99d92]" />}
                      Role: {user.role}
                    </span>
                  </div>

                  <div className="py-1">
                    {navLinks.map((link) => (
                      <Link
                        key={link.path}
                        to={link.path}
                        onClick={() => setUserDropdownOpen(false)}
                        className="flex items-center gap-2.5 px-4 py-2 text-xs font-semibold text-stone-700 dark:text-[#c8bbb0] hover:bg-stone-100 dark:hover:bg-[#38322d] transition-colors tracking-wider"
                      >
                        <link.icon className="w-4 h-4 text-orange-700 dark:text-[#789b86]" />
                        {link.name}
                      </Link>
                    ))}
                  </div>

                  <div className="border-t border-stone-100 dark:border-[#403933] pt-1">
                    <button
                      onClick={handleLogout}
                      className="w-full flex items-center gap-2 px-4 py-2 text-xs text-rose-700 dark:text-[#c98d89] hover:bg-rose-50 dark:hover:bg-[#3b2424]/60 transition-colors text-left font-semibold"
                    >
                      <LogOut className="w-4 h-4" />
                      SIGN OUT
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <Link
              to="/auth"
              className="px-5 py-2.5 rounded-full bg-stone-950 text-white dark:bg-[#315c49] dark:text-[#f3ece4] text-xs font-bold tracking-wider hover:bg-orange-700 dark:hover:bg-[#789b86] transition-all shadow-md"
            >
              SIGN IN
            </Link>
          )}

          {/* Mobile hamburger button */}
          <button
            type="button"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="md:hidden p-2 text-stone-700 dark:text-[#c8bbb0] rounded-full bg-white dark:bg-[#25211e] border border-stone-300 dark:border-[#403933]"
          >
            {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>
      </div>

      {/* Mobile Menu Dropdown */}
      {mobileMenuOpen && (
        <div className="md:hidden border-t border-stone-200 dark:border-[#403933] bg-[#F5F0E8] dark:bg-[#181512] px-4 py-4 space-y-2">
          {navLinks.map((link) => (
            <Link
              key={link.path}
              to={link.path}
              onClick={() => setMobileMenuOpen(false)}
              className="flex items-center gap-3 px-4 py-3 rounded-full text-xs font-bold tracking-widest text-stone-950 dark:text-[#f3ece4] bg-white dark:bg-[#25211e] border border-stone-200 dark:border-[#403933]"
            >
              <link.icon className="w-4 h-4 text-orange-700 dark:text-[#789b86]" />
              {link.name}
            </Link>
          ))}
        </div>
      )}
    </header>
  )
}
