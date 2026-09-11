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
  Moon,
  FolderKanban,
  Download,
  Terminal
} from 'lucide-react'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useTheme } from '../../context/ThemeContext'
import { useLanguage } from '../../context/LanguageContext'
import { ProfileModal } from '../auth/ProfileModal'

const getNavByRole = (t) => ({
  engineer: [
    { name: t("nav.search"), path: "/search", icon: Search },
    { name: t("nav.draft"), path: "/datasets/draft", icon: FolderKanban },
    { name: t("nav.datasets"), path: "/datasets", icon: Download }
  ],
  admin: [
    { name: t("nav.ingest"), path: "/ingest", icon: Upload },
    { name: t("nav.search"), path: "/search", icon: Search },
    { name: t("nav.admin"), path: "/admin", icon: LayoutDashboard }
  ]
})

const getAnonNav = (t) => [{ name: t("nav.search"), path: "/search", icon: Search }]

export const Header = () => {
  const { user, isAuthenticated, logout } = useAuth()
  const { addToast } = useToast()
  const { toggleTheme, isDark } = useTheme()
  const { language, setLanguage, t } = useLanguage()
  const location = useLocation()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [userDropdownOpen, setUserDropdownOpen] = useState(false)
  const [profileModalOpen, setProfileModalOpen] = useState(false)

  const handleLogout = () => {
    logout()
    addToast('Logged out successfully', 'info')
    setUserDropdownOpen(false)
  }

  const handleToggleTheme = () => {
    toggleTheme()
    const nextMode = isDark ? 'Light Mode' : 'Dark Mode'
    addToast(`Switched to ${nextMode}`, 'info')
  }

  const navConfig = getNavByRole(t)
  const anonNav = getAnonNav(t)
  const displayLinks = isAuthenticated
    ? navConfig[user?.role] || anonNav
    : anonNav

  const RoleIcon = user?.role === 'admin' ? Shield : User

  return (
    <header className="sticky top-0 z-40 w-full bg-[#F7F4EE]/95 dark:bg-[#141210]/95 backdrop-blur-md border-b-2 border-black">
      <div className="max-w-[1700px] mx-auto px-4 sm:px-8 h-16 flex items-center justify-between">
        {/* Left Branding & Main Navigation */}
        <div className="flex items-center gap-8">
          <Link
            to="/"
            className="flex items-center gap-2 group tracking-tighter"
            aria-label="SceneSearch Home"
          >
            <div className="w-8 h-8 bg-black text-white flex items-center justify-center font-mono font-black text-base border border-black shadow-[2px_2px_0px_0px_#FF5500] group-hover:bg-[#FF5500] group-hover:text-black transition-colors">
              S
            </div>
            <span className="font-black text-lg tracking-tight uppercase font-mono">
              SCENESEARCH<span className="text-[#FF5500]">.AI</span>
            </span>
          </Link>

          {/* Desktop Navigation Links */}
          <nav className="hidden md:flex items-center gap-1">
            {displayLinks.map((link) => {
              const Icon = link.icon
              const isActive = location.pathname === link.path
              return (
                <Link
                  key={link.name}
                  to={link.path}
                  className={`flex items-center gap-2 px-3.5 py-1.5 font-mono text-xs font-black uppercase tracking-wider border-2 transition-all ${
                    isActive
                      ? 'bg-black text-white border-black shadow-[2px_2px_0px_0px_#FF5500]'
                      : 'bg-white/60 dark:bg-stone-900 border-black/30 dark:border-stone-700 text-stone-800 dark:text-stone-300 hover:border-black hover:bg-white hover:text-black dark:hover:bg-stone-800 dark:hover:text-white'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  {link.name}
                </Link>
              )
            })}
          </nav>
        </div>

        {/* Right Controls & User Profile */}
        <div className="flex items-center gap-3">
          {/* Cluster Status Badge */}
          <div className="hidden xl:flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-stone-900 border-2 border-black text-black dark:text-white font-mono text-[10px] font-black uppercase tracking-wider shadow-[2px_2px_0px_0px_#000]">
            <span className="w-2 h-2 rounded-full bg-[#00D084] animate-ping" />
            <span>{t('nav.online')}</span>
          </div>

          {/* Language Toggle (EN / VI) */}
          <div className="flex items-center border-2 border-black font-mono text-xs font-black shadow-[2px_2px_0px_0px_#000] bg-white dark:bg-stone-900">
            <button
              type="button"
              onClick={() => {
                if (language !== "en") {
                  setLanguage("en")
                  addToast("Switched language to English", "info")
                }
              }}
              className={`px-2 py-1 transition-colors cursor-pointer ${
                language === "en"
                  ? "bg-black text-white dark:bg-[#FF5500] dark:text-black"
                  : "text-stone-600 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800"
              }`}
              title="Switch to English"
              aria-label="Switch language to English"
            >
              EN
            </button>
            <div className="w-[1.5px] h-3.5 bg-black/40 dark:bg-stone-700" />
            <button
              type="button"
              onClick={() => {
                if (language !== "vi") {
                  setLanguage("vi")
                  addToast("Đã chuyển ngôn ngữ sang Tiếng Việt", "info")
                }
              }}
              className={`px-2 py-1 transition-colors cursor-pointer ${
                language === "vi"
                  ? "bg-black text-white dark:bg-[#FF5500] dark:text-black"
                  : "text-stone-600 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800"
              }`}
              title="Chuyển sang Tiếng Việt"
              aria-label="Switch language to Vietnamese"
            >
              VI
            </button>
          </div>

          {/* Theme Mode Toggle */}
          <button
            type="button"
            onClick={handleToggleTheme}
            className="p-2 bg-white dark:bg-stone-900 border-2 border-black text-black dark:text-white hover:bg-[#FF5500] hover:text-black dark:hover:bg-[#FF5500] dark:hover:text-black shadow-[2px_2px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all cursor-pointer flex items-center justify-center"
            title={t(isDark ? "theme.switch_to_light" : "theme.switch_to_dark")}
            aria-label="Toggle Theme Mode"
          >
            {isDark ? (
              <Sun className="w-4 h-4 text-amber-300" />
            ) : (
              <Moon className="w-4 h-4 text-black" />
            )}
          </button>

          {/* User Profile / Auth State */}
          {isAuthenticated ? (
            <div className="relative">
              <button
                type="button"
                onClick={() => setUserDropdownOpen(!userDropdownOpen)}
                className="flex items-center gap-2.5 px-3 py-1.5 bg-white dark:bg-stone-900 border-2 border-black shadow-[3px_3px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all cursor-pointer"
              >
                <img
                  src={user.avatar}
                  alt={user.name}
                  className="w-6 h-6 rounded-full border border-black object-cover"
                />
                <div className="hidden sm:flex flex-col text-left">
                  <span className="font-mono text-xs font-black text-black dark:text-white leading-none">
                    {user.name}
                  </span>
                  <span
                    className={`text-[9px] font-mono font-black uppercase mt-0.5 ${
                      user.role === 'admin' ? 'text-[#FF5500]' : 'text-[#00D084]'
                    }`}
                  >
                    [{user.role}]
                  </span>
                </div>
              </button>

              {userDropdownOpen && (
                <div className="absolute right-0 mt-2 w-64 bg-[#F7F4EE] dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] py-2 z-50 animate-fadeIn font-mono">
                  <div className="px-4 py-3 border-b-2 border-black">
                    <p className="text-xs font-black text-black dark:text-white uppercase">{user.name}</p>
                    <p className="text-[11px] text-stone-600 dark:text-stone-400 truncate">{user.email}</p>
                    <div className="inline-flex items-center gap-1.5 mt-2 px-2 py-0.5 bg-white dark:bg-stone-900 border border-black text-[10px] font-black uppercase">
                      <RoleIcon className="w-3 h-3 text-[#FF5500]" />
                      <span>ROLE: {user.role}</span>
                    </div>
                  </div>

                  <div className="py-2 space-y-1">
                    <button
                      type="button"
                      onClick={() => {
                        setUserDropdownOpen(false)
                        setProfileModalOpen(true)
                      }}
                      className="w-full flex items-center gap-2.5 px-4 py-2 text-xs font-black text-black dark:text-stone-200 hover:bg-[#FF5500] hover:text-black transition-colors cursor-pointer text-left uppercase"
                    >
                      <User className="w-4 h-4 text-[#FF5500]" />
                      {t('nav.profile')}
                    </button>

                    {displayLinks.map((link) => (
                      <Link
                        key={`${link.name}-dd`}
                        to={link.path}
                        onClick={() => setUserDropdownOpen(false)}
                        className="flex items-center gap-2.5 px-4 py-2 text-xs font-bold text-black dark:text-stone-200 hover:bg-black hover:text-white transition-colors"
                      >
                        <link.icon className="w-4 h-4 text-[#FF5500]" />
                        {link.name}
                      </Link>
                    ))}
                    <Link
                      to="/"
                      onClick={() => setUserDropdownOpen(false)}
                      className="flex items-center gap-2.5 px-4 py-2 text-xs font-bold text-black dark:text-stone-200 hover:bg-black hover:text-white transition-colors"
                    >
                      <Terminal className="w-4 h-4 text-[#00D084]" />
                      {t('nav.about')}
                    </Link>
                  </div>

                  <div className="border-t-2 border-black pt-1 px-2">
                    <button
                      type="button"
                      onClick={handleLogout}
                      className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-red-100 dark:bg-red-950/40 border border-red-600 text-red-900 dark:text-red-300 hover:bg-red-600 hover:text-white text-xs font-black uppercase transition-all cursor-pointer"
                    >
                      <LogOut className="w-3.5 h-3.5" />
                      {t('nav.logout')}
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <Link
              to="/auth?mode=login"
              className="px-5 py-2 bg-black text-white font-mono text-xs font-black uppercase tracking-wider border-2 border-black shadow-[3px_3px_0px_0px_#FF5500] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all"
            >
              {t('nav.login')}
            </Link>
          )}

          {/* Mobile Menu Button */}
          <button
            type="button"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="md:hidden p-2 bg-white dark:bg-stone-900 border-2 border-black text-black dark:text-white"
          >
            {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>
      </div>

      {/* Mobile Drawer */}
      {mobileMenuOpen && (
        <div className="md:hidden border-t-2 border-black bg-[#F7F4EE] dark:bg-[#141210] p-4 space-y-2 font-mono">
          {isAuthenticated && (
            <button
              type="button"
              onClick={() => {
                setMobileMenuOpen(false)
                setProfileModalOpen(true)
              }}
              className="w-full flex items-center gap-3 px-4 py-3 bg-white dark:bg-stone-900 border-2 border-black text-xs font-black uppercase shadow-[2px_2px_0px_0px_#000] text-left"
            >
              <User className="w-4 h-4 text-[#FF5500]" />
              MY {t('nav.profile')}
            </button>
          )}
          {displayLinks.map((link) => (
            <Link
              key={`${link.name}-m`}
              to={link.path}
              onClick={() => setMobileMenuOpen(false)}
              className="flex items-center gap-3 px-4 py-3 bg-white dark:bg-stone-900 border-2 border-black text-xs font-black uppercase shadow-[2px_2px_0px_0px_#000]"
            >
              <link.icon className="w-4 h-4 text-[#FF5500]" />
              {link.name}
            </Link>
          ))}
        </div>
      )}

      {/* User Profile Modal */}
      <ProfileModal
        isOpen={profileModalOpen}
        onClose={() => setProfileModalOpen(false)}
      />
    </header>
  )
}
