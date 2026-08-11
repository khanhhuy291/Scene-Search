import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import { ToastProvider } from './context/ToastContext'
import { ThemeProvider } from './context/ThemeContext'
import { Header } from './components/layout/Header'
import { ProtectedRoute } from './components/layout/ProtectedRoute'

import { AuthPage } from './pages/AuthPage'
import { SearchPage } from './pages/SearchPage'
import { IngestionPage } from './pages/IngestionPage'
import { AdminPage } from './pages/AdminPage'
import { NotFoundPage } from './pages/NotFoundPage'

import './styles/main.css'

export default function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <ToastProvider>
          <AuthProvider>
            <div className="min-h-screen flex flex-col bg-[#F5F0E8] dark:bg-[#181512] text-stone-900 dark:text-[#f3ece4] selection:bg-orange-100 dark:selection:bg-[#1d352b] selection:text-orange-900 dark:selection:text-[#c1d2c6] transition-colors duration-300">
              <Header />

              <div className="flex-1">
                <Routes>
                  {/* Public Semantic Search Default Route */}
                  <Route path="/" element={<Navigate to="/search" replace />} />
                  <Route path="/search" element={<SearchPage />} />

                  {/* Authentication Page */}
                  <Route path="/auth" element={<AuthPage />} />

                  {/* Protected Ingestion Workflow (User/Admin) */}
                  <Route
                    path="/ingest"
                    element={
                      <ProtectedRoute>
                        <IngestionPage />
                      </ProtectedRoute>
                    }
                  />

                  {/* Protected Admin Dashboard (Admin Only) */}
                  <Route
                    path="/admin"
                    element={
                      <ProtectedRoute requireAdmin={true}>
                        <AdminPage />
                      </ProtectedRoute>
                    }
                  />

                  {/* 404 Handler */}
                  <Route path="*" element={<NotFoundPage />} />
                </Routes>
              </div>
            </div>
          </AuthProvider>
        </ToastProvider>
      </ThemeProvider>
    </BrowserRouter>
  )
}
