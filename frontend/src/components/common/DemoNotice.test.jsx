import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { DemoNotice } from './DemoNotice'

describe('DemoNotice', () => {
  it('identifies live search, JWT auth, and dataset downloads', () => {
    render(<DemoNotice />)

    expect(screen.getByRole('status')).toHaveTextContent(/auth/i)
    expect(screen.getByRole('status')).toHaveTextContent(/download/i)
    expect(screen.getByRole('status')).toHaveTextContent(/search/i)
  })
})
