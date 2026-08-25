import React from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import { DatasetProvider } from './context/DatasetContext'
import { ToastProvider } from './context/ToastContext'
import { ThemeProvider } from './context/ThemeContext'
import { Header } from './components/layout/Header'
import { ProtectedRoute } from './components/layout/ProtectedRoute'
import { DemoNotice } from './components/common/DemoNotice'

import { LandingPage } from './pages/LandingPage'
import { AuthPage } from './pages/AuthPage'
import { SearchPage } from './pages/SearchPage'
import { IngestionPage } from './pages/IngestionPage'
import { IngestionJobPage } from './pages/IngestionJobPage'
import { AdminPage } from './pages/AdminPage'
import { DatasetDraftPage } from './pages/DatasetDraftPage'
import { MyDatasetsPage } from './pages/MyDatasetsPage'
import { EvalPage } from './pages/EvalPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { ChatWidget } from './components/chat/ChatWidget'

import './styles/main.css'

function AppContent() {
  const location = useLocation()
  const isStandaloneBrutalist =
    location.pathname === '/' || location.pathname === '/landing' || location.pathname === '/auth'

  return (
    <div className={`min-h-screen flex flex-col ${isStandaloneBrutalist ? 'bg-[#F7F4EE]' : 'bg-[#F5F0E8] dark:bg-[#181512]'} text-stone-900 dark:text-[#f3ece4] selection:bg-orange-100 dark:selection:bg-[#1d352b] selection:text-orange-900 dark:selection:text-[#c1d2c6] transition-colors duration-300`}>
      {!isStandaloneBrutalist && <DemoNotice />}
      {!isStandaloneBrutalist && <Header />}

      <div className="flex-1">
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/landing" element={<LandingPage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/auth" element={<AuthPage />} />

          <Route
            path="/datasets/draft"
            element={
              <ProtectedRoute roles={['engineer']}>
                <DatasetDraftPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/datasets"
            element={
              <ProtectedRoute roles={['engineer', 'admin']}>
                <MyDatasetsPage />
              </ProtectedRoute>
            }
          />
          <Route path="/review" element={<Navigate to="/datasets" replace />} />
          <Route
            path="/eval"
            element={
              <ProtectedRoute roles={['admin']}>
                <EvalPage />
              </ProtectedRoute>
            }
          />

          <Route
            path="/ingest"
            element={
              <ProtectedRoute roles={['admin']}>
                <IngestionPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/ingest/jobs/:taskId"
            element={
              <ProtectedRoute roles={['admin']}>
                <IngestionJobPage />
              </ProtectedRoute>
            }
          />

          <Route
            path="/admin"
            element={
              <ProtectedRoute roles={['admin']}>
                <AdminPage />
              </ProtectedRoute>
            }
          />

          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </div>

      <ChatWidget />
    </div>
  )
}

export default function App() {
  const basename = (import.meta.env.BASE_URL || '/').replace(/\/$/, '') || '/'

  return (
    <BrowserRouter basename={basename === '/' ? undefined : basename}>
      <ThemeProvider>
        <ToastProvider>
          <AuthProvider>
            <DatasetProvider>
              <AppContent />
            </DatasetProvider>
          </AuthProvider>
        </ToastProvider>
      </ThemeProvider>
    </BrowserRouter>
  )
}
