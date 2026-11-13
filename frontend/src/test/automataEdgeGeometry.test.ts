import { describe, expect, it } from 'vitest'
import { getSelfLoopGeometry } from '../components/automataEdgeGeometry'

describe('getSelfLoopGeometry', () => {
  it('creates an elevated curved path with a label centered above it', () => {
    const geometry = getSelfLoopGeometry(147, 200, 53, 200)

    expect(geometry.path).toBe('M 147 200 C 151 50, 49 50, 53 200')
    expect(geometry.labelX).toBe(100)
    expect(geometry.labelY).toBe(87)
    expect(geometry.labelY).toBeLessThan(200)
  })
})
