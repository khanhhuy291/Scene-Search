import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { LandingPage } from '../pages/LandingPage'
import { AuthProvider } from '../context/AuthContext'
import { ToastProvider } from '../context/ToastContext'

describe('LandingPage Hero Section & Brutalist Auth Integration', () => {
  it('renders brutalist hero headline, nav, and floating pill search bar without requiring authentication', () => {
    render(
      <MemoryRouter>
        <ToastProvider>
          <AuthProvider>
            <LandingPage />
          </AuthProvider>
        </ToastProvider>
      </MemoryRouter>
    )

    // Requirement 1: Top Nav with monospaced link & solid black SIGN UP button
    expect(screen.getByRole('button', { name: /SIGN UP/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /^INDEX$/i })).toBeInTheDocument()

    // Requirement 2: Massive ultra-bold headline
    const h1 = screen.getByRole('heading', { level: 1 })
    expect(h1).toHaveTextContent(/Search/i)
    expect(h1).toHaveTextContent(/Beautifully/i)
    expect(h1).toHaveTextContent(/Purposefully/i)

    // Requirement 3: Right panel titled "DYSTOPIAN FUTURES"
    expect(screen.getByText(/DYSTOPIAN FUTURES/i)).toBeInTheDocument()

    // Requirement 4: Floating geometric elements
    expect(screen.getByText(/15K\+/i)).toBeInTheDocument()
    expect(screen.getByText(/AI EMBEDDINGS/i)).toBeInTheDocument()
    expect(screen.getByText(/REAL-TIME QDRANT/i)).toBeInTheDocument()

    // Requirement 5: Floating pill search bar
    expect(screen.getByPlaceholderText(/SEARCH ANYTHING/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /SEARCH/i })).toBeInTheDocument()
  })

  it('opens brutalist auth modal when clicking SIGN UP and allows 1-click demo autofill in SIGN IN mode', () => {
    render(
      <MemoryRouter>
        <ToastProvider>
          <AuthProvider>
            <LandingPage />
          </AuthProvider>
        </ToastProvider>
      </MemoryRouter>
    )

    // Click SIGN UP button in header
    const signUpBtn = screen.getAllByRole('button', { name: /SIGN UP/i })[0]
    fireEvent.click(signUpBtn)

    // Modal should be open with auth portal
    expect(screen.getByText(/SCENESEARCH \/\/ AUTH PORTAL/i)).toBeInTheDocument()
    expect(screen.getByText(/\[02 \/\/ CREATE ACCOUNT\]/i)).toBeInTheDocument()

    // Switch to SIGN IN tab
    const signInTab = screen.getByRole('button', { name: /\[01 \/\/ SIGN IN\]/i })
    fireEvent.click(signInTab)

    // Demo Autofill should be visible
    expect(screen.getByText(/1-CLICK DEMO AUTOFILL:/i)).toBeInTheDocument()

    // Click Admin autofill
    const adminAutofill = screen.getByRole('button', { name: /ADMIN \(INGEST\)/i })
    fireEvent.click(adminAutofill)

    // Input should contain admin email
    const emailInput = screen.getByPlaceholderText(/name@scenesearch.ai/i)
    expect(emailInput.value).toBe('admin@scenesearch.ai')
  })

  it('renders dataset section with BDD-100K, Kaggle 20GB subset, and 88-query testset', () => {
    render(
      <MemoryRouter>
        <ToastProvider>
          <AuthProvider>
            <LandingPage />
          </AuthProvider>
        </ToastProvider>
      </MemoryRouter>
    )

    // Dataset section header
    expect(screen.getByText(/AUTONOMOUS DRIVING DATASET CORPUS/i)).toBeInTheDocument()
    expect(screen.getByText(/BDD-100K · KAGGLE 20GB SUBSET · 88 TESTSET PAIRS/i)).toBeInTheDocument()

    // BDD-100K & Kaggle links
    const bddLink = screen.getByRole('link', { name: /BDD-100K SITE/i })
    expect(bddLink).toHaveAttribute('href', 'http://bdd-data.berkeley.edu/')

    const kaggleLink = screen.getByRole('link', { name: /KAGGLE 20GB DATASET/i })
    expect(kaggleLink).toHaveAttribute('href', 'https://www.kaggle.com/datasets/robikscube/driving-video-with-object-tracking')

    // 88 testset golden pairs card
    expect(screen.getByText(/BENCHMARK TESTSET \(88 QUERY-FRAME PAIRS\)/i)).toBeInTheDocument()
  })

  it('renders retrieval model benchmark section with SigCLIP, Qwen3-VL 2B, Hybrid, and reranker ablation', () => {
    render(
      <MemoryRouter>
        <ToastProvider>
          <AuthProvider>
            <LandingPage />
          </AuthProvider>
        </ToastProvider>
      </MemoryRouter>
    )

    // Benchmark title and subtitle
    expect(screen.getByText(/RETRIEVAL MODEL BENCHMARK/i)).toBeInTheDocument()
    expect(screen.getByText(/Comparison of/i)).toBeInTheDocument()

    // Main comparison table headers
    expect(screen.getByText(/MAIN RETRIEVAL COMPARISON \(VIDEO-LEVEL\)/i)).toBeInTheDocument()
    expect(screen.getAllByText(/Qwen3-VL Embedding 2B/i).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText(/SigCLIP/i).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText(/Hybrid Retrieval/i).length).toBeGreaterThanOrEqual(1)

    // Qwen3-VL verified results
    expect(screen.getAllByText('73.86%').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('84.09%').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('89.77%').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('93.18%').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('95.45%').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('96.59%').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('0.8016').length).toBeGreaterThanOrEqual(1)

    // Frame-Level HitRate & MRR Comparison
    expect(screen.getByText(/FRAME-LEVEL HITRATE & MRR COMPARISON/i)).toBeInTheDocument()
    expect(screen.getAllByText('37.50%').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('3.41%').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('7.95%').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('0.518817').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('0.220510').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('0.071342').length).toBeGreaterThanOrEqual(1)

    // Evaluation Granularity Tiers
    expect(screen.getAllByText(/Video-Level/i).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText(/Frame-Tolerant/i).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText(/Frame-Exact/i).length).toBeGreaterThanOrEqual(1)

    // Separate Reranker ablation study
    expect(screen.getByText(/RERANKER EXPERIMENT \/\/ QWEN3-VL-RERANKER-2B/i)).toBeInTheDocument()
    expect(screen.getByText(/ABLATION CONCLUSION/i)).toBeInTheDocument()
    expect(screen.getByText(/NO IMPROVEMENT OBSERVED/i)).toBeInTheDocument()

    // Final UI decision message
    expect(
      screen.getByText(/Qwen3-VL Embedding 2B was selected as the default retrieval model for online SceneSearch search, providing a strong balance between retrieval quality and search efficiency./i)
    ).toBeInTheDocument()
  })
})
