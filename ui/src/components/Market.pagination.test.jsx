/*
 * Regression battery for the pagination that never left page 1.
 *
 * Measured before the fix, against the running stack with 299 properties
 * across 6 pages: clicking "Next" left "Page 1 / 6" on screen indefinitely,
 * with the same first card. The click updated the page in state, then a
 * `setTimeout(loadListings, 100)` ran the closure from the render that had
 * handled the click, so the request still carried the old page, and writing
 * the response's page back into state undid the increment.
 *
 * The invariant these tests hold: the page the component asks the API for is
 * the page the user asked for, and the page the user asked for is the one
 * displayed.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import Market from './Market'

const { getListings } = vi.hoisted(() => ({ getListings: vi.fn() }))

vi.mock('../api', () => ({ api: { getListings, buyProperty: vi.fn(), deleteProperty: vi.fn(), createProperty: vi.fn() } }))

const TOTAL = 299
const PER_PAGE = 50

function pageOf(page) {
  return {
    // Shaped from a real /trading/listings response, so the card renders the
    // same fields it renders in production.
    items: [
      {
        propertyId: `page${page}property`,
        zone: `Zone for page ${page}`,
        type: 'apartment',
        surface: 66.68,
        basePpm: 1800,
        price: 148472.8,
        pricePerM2: 2226.65,
        zoneTrendAnnual: 0,
        epcScore: 40.2,
        stateScore: 49.6,
        kitchenScore: 23.3,
        bathScore: 49.4,
        qualityScore: 40.6,
        estimated1YearPrice: 152000.0,
        estimated1YearGain: 3527.2,
        estimated1YearGainPct: 2.4,
      },
    ],
    total: TOTAL,
    page,
    limit: PER_PAGE,
    totalPages: Math.ceil(TOTAL / PER_PAGE),
  }
}

function requestedPages() {
  return getListings.mock.calls.map(([query]) => query.page)
}

function renderMarket() {
  return render(<Market onPurchase={vi.fn()} showMessage={vi.fn()} />)
}

beforeEach(() => {
  getListings.mockImplementation(async (query) => pageOf(query.page ?? 1))
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('paging through the market', () => {
  it('asks the API for page 2 when the user clicks Next', async () => {
    // The exact reported case.
    const user = userEvent.setup()
    renderMarket()
    await screen.findByText('Zone for page 1')

    await user.click(screen.getByRole('button', { name: /next/i }))

    await waitFor(() => expect(requestedPages()).toContain(2))
  })

  it('shows page 2 after the user clicks Next', async () => {
    const user = userEvent.setup()
    renderMarket()
    await screen.findByText('Zone for page 1')

    await user.click(screen.getByRole('button', { name: /next/i }))

    expect(await screen.findByText('Zone for page 2')).toBeInTheDocument()
    expect(screen.getByText(/Page 2 \/ 6/)).toBeInTheDocument()
  })

  it('never displays a page it did not request', async () => {
    // The invariant, stated generally: whatever sequence of clicks happens,
    // the page on screen is the page of the last answered request.
    const user = userEvent.setup()
    renderMarket()
    await screen.findByText('Zone for page 1')

    await user.click(screen.getByRole('button', { name: /next/i }))
    await screen.findByText('Zone for page 2')
    await user.click(screen.getByRole('button', { name: /next/i }))
    await screen.findByText('Zone for page 3')

    const lastRequested = requestedPages().at(-1)
    expect(screen.getByText(new RegExp(`Page ${lastRequested} / 6`))).toBeInTheDocument()
  })

  it('walks back with Previous', async () => {
    const user = userEvent.setup()
    renderMarket()
    await screen.findByText('Zone for page 1')

    await user.click(screen.getByRole('button', { name: /next/i }))
    await screen.findByText('Zone for page 2')
    await user.click(screen.getByRole('button', { name: /previous/i }))

    expect(await screen.findByText('Zone for page 1')).toBeInTheDocument()
  })

  it('disables Previous on the first page', async () => {
    renderMarket()
    await screen.findByText('Zone for page 1')

    expect(screen.getByRole('button', { name: /previous/i })).toBeDisabled()
  })

  it('disables Next on the last page', async () => {
    // The upper boundary: 299 properties at 50 per page is 6 pages.
    const user = userEvent.setup()
    renderMarket()
    await screen.findByText('Zone for page 1')

    for (const page of [2, 3, 4, 5, 6]) {
      await user.click(screen.getByRole('button', { name: /next/i }))
      await screen.findByText(`Zone for page ${page}`)
    }

    expect(screen.getByRole('button', { name: /next/i })).toBeDisabled()
  })

  it('goes back to the first page when a new search is run', async () => {
    // Page 4 of the old result set says nothing about the new one, and asking
    // for it can land past the end.
    const user = userEvent.setup()
    renderMarket()
    await screen.findByText('Zone for page 1')

    await user.click(screen.getByRole('button', { name: /next/i }))
    await screen.findByText('Zone for page 2')

    await user.selectOptions(screen.getByLabelText(/zone/i), 'Ixelles')
    await user.click(screen.getByRole('button', { name: /^search$/i }))

    await waitFor(() => {
      const [query] = getListings.mock.calls.at(-1)
      expect(query.page).toBe(1)
      expect(query.zone).toBe('Ixelles')
    })
  })

  it('requests each page exactly once per click', async () => {
    // A duplicated request is the signature of the two competing code paths
    // (an effect and a hand-scheduled callback) that caused the defect.
    const user = userEvent.setup()
    renderMarket()
    await screen.findByText('Zone for page 1')

    await user.click(screen.getByRole('button', { name: /next/i }))
    await screen.findByText('Zone for page 2')

    expect(requestedPages()).toEqual([1, 2])
  })
})
