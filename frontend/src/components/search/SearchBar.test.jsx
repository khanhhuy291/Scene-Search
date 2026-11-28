import React, { useState } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { SearchBar, SEARCH_MODES } from './SearchBar'

vi.mock('../../context/LanguageContext', () => ({
  useLanguage: () => ({ t: (key) => key, isVietnamese: false })
}))
const Harness = ({ onSearch }) => {
  const [options, setOptions] = useState({ mode: 'siglip_qwen_rrf', limit: 24 })
  return <SearchBar initialQuery="rainy street" options={options} onOptionsChange={setOptions} onSearch={onSearch} />
}

describe('explicit vector modes', () => {
  it('submits exactly five selected modes without query rewriting', () => {
    const onSearch = vi.fn()
    render(<Harness onSearch={onSearch} />)
    expect(SEARCH_MODES.map((mode) => mode.id)).toEqual(['siglip', 'qwen', 'caption', 'siglip_qwen_rrf', 'qwen_caption_rrf'])
    for (const mode of SEARCH_MODES) {
      const button = screen.getByRole('button', { name: mode.label, exact: true })
      fireEvent.click(button)
      expect(button).toHaveAttribute('aria-pressed', 'true')
      fireEvent.submit(screen.getByRole('textbox').closest('form'))
      expect(onSearch).toHaveBeenLastCalledWith('rainy street', { mode: mode.id, limit: 24 })
    }
    expect(screen.queryByText('VISUAL ONLY')).not.toBeInTheDocument()
    expect(screen.queryByText('HYBRID')).not.toBeInTheDocument()
  })
  it('keeps selection and page size after remounting the compact bar', () => {
    const onSearch = vi.fn()
    const props = { options: { mode: 'qwen_caption_rrf', limit: 48 }, initialQuery: 'rain', onSearch }
    const { rerender } = render(<SearchBar key="landing" {...props} />)
    rerender(<SearchBar key="workspace" {...props} compact />)
    expect(screen.getByRole('button', { name: 'RRF Qwen + Caption', exact: true })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.submit(screen.getByRole('textbox').closest('form'))
    expect(onSearch).toHaveBeenLastCalledWith('rain', { mode: 'qwen_caption_rrf', limit: 48 })
  })
})
