import React, { useState } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { SearchBar } from './SearchBar'

vi.mock('../../context/LanguageContext', () => ({
  useLanguage: () => ({ t: (key) => key, isVietnamese: false })
}))

const Harness = ({ onSearch }) => {
  const [options, setOptions] = useState({ mode: 'hybrid', limit: 24 })
  return <SearchBar initialQuery="rainy street" options={options} onOptionsChange={setOptions} onSearch={onSearch} />
}

describe('vector search options', () => {
  it('shows exactly three retrieval modes and submits the selected model', () => {
    const onSearch = vi.fn()
    render(<Harness onSearch={onSearch} />)
    expect(screen.getByRole('button', { name: 'SigLIP + Qwen + RRF' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.queryByText('CAPTION ONLY')).not.toBeInTheDocument()
    expect(screen.queryByText('VISUAL ONLY')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Qwen', exact: true }))
    expect(screen.getByRole('button', { name: 'Qwen', exact: true })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.submit(screen.getByRole('textbox').closest('form'))
    expect(onSearch).toHaveBeenLastCalledWith('rainy street', { mode: 'qwen', limit: 24 })
    fireEvent.click(screen.getByRole('button', { name: 'SigLIP', exact: true }))
    fireEvent.click(screen.getByRole('button', { name: '48', exact: true }))
    fireEvent.submit(screen.getByRole('textbox').closest('form'))
    expect(onSearch).toHaveBeenLastCalledWith('rainy street', { mode: 'siglip', limit: 48 })
  })

  it('retains the parent selection after remounting the compact search bar', () => {
    const onSearch = vi.fn()
    const props = { options: { mode: 'qwen', limit: 48 }, initialQuery: 'rain', onSearch }
    const { rerender } = render(<SearchBar key="landing" {...props} />)
    rerender(<SearchBar key="workspace" {...props} compact />)
    expect(screen.getByRole('button', { name: 'Qwen', exact: true })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.submit(screen.getByRole('textbox').closest('form'))
    expect(onSearch).toHaveBeenLastCalledWith('rain', { mode: 'qwen', limit: 48 })
  })
})
