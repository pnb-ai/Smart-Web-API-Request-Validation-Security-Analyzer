import { expect, test } from '@playwright/test'

test('workspace navigation, learning panel, cross-feature flow, and guided demo', async ({ page }) => {
  await page.goto('/')
  const tour = page.getByRole('dialog', { name: 'Getting started tour' })
  if (await tour.isVisible().catch(() => false)) await tour.getByRole('button', { name: 'Skip tour' }).click()

  await page.getByRole('button', { name: 'Learn about this page' }).click()
  await expect(page.getByRole('complementary', { name: 'Automata Builder theory' })).toContainText('Finite automata')
  await page.getByRole('button', { name: 'Close Learn panel' }).click()

  await page.getByLabel('Load example').selectOption('0')
  await expect(page.locator('.automata-state').first()).toContainText('even')
  await page.getByRole('button', { name: 'Simulator', exact: true }).last().click()
  await expect(page.getByRole('heading', { name: 'Simulator' })).toBeVisible()
  await page.getByRole('button', { name: 'Transform', exact: true }).last().click()
  await expect(page.getByRole('heading', { name: 'Transform & Optimize', exact: true }).first()).toBeVisible()
  await page.getByRole('button', { name: 'Equivalence', exact: true }).last().click()
  await expect(page.getByRole('heading', { name: 'Do these rules accept the same language?' })).toBeVisible()
  await expect(page.getByText(/Uses the automaton currently in Builder/)).toBeVisible()

  await page.getByRole('button', { name: 'Run Demo Story' }).click()
  await expect(page.locator('.demo-status')).toContainText('Demo complete', { timeout: 60_000 })
  await expect(page.locator('.demo-status')).toContainText('shortest witness: ad')
  await expect(page.getByRole('heading', { name: 'Transform & Optimize', exact: true }).first()).toBeVisible()
})

test('command palette searches and opens a feature', async ({ page }) => {
  await page.goto('/')
  const tour = page.getByRole('dialog', { name: 'Getting started tour' })
  if (await tour.isVisible().catch(() => false)) await tour.getByRole('button', { name: 'Skip tour' }).click()
  await page.keyboard.press('Control+k')
  await page.getByRole('textbox', { name: 'Search pages' }).fill('Security Analyzer')
  await page.keyboard.press('Enter')
  await expect(page.getByRole('heading', { name: 'Security Analyzer', exact: true })).toBeVisible()
})

test('workspaces save, load, export, and import JSON', async ({ page }) => {
  await page.goto('/')
  const tour = page.getByRole('dialog', { name: 'Getting started tour' })
  if (await tour.isVisible().catch(() => false)) await tour.getByRole('button', { name: 'Skip tour' }).click()
  await page.getByLabel('Load example').selectOption('0')
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await page.getByRole('button', { name: 'New', exact: true }).click()
  await page.getByLabel('Workspace name').fill('Second workspace')
  await page.getByRole('button', { name: 'Create workspace' }).click()
  await page.getByLabel('Saved workspace').selectOption({ label: 'My Workspace' })
  await expect(page.locator('.automata-state').first()).toContainText('even')

  const downloadReady = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export workspace JSON' }).click()
  expect((await downloadReady).suggestedFilename()).toMatch(/\.json$/)

  const data = { name: 'Imported', automaton: { type: 'DFA', states: [], alphabet: [], transitions: [] }, regexes: ['a*'], requests: ['GET / HTTP/1.1'] }
  await page.locator('.workspace-tools input[type="file"]').setInputFiles({ name: 'workspace.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(data)) })
  await expect(page.getByLabel('Saved workspace')).toHaveValue(/workspace-/)
})

test('builder stays responsive with a 200-state symbol-class automaton', async ({ page }) => {
  await page.goto('/')
  const tour = page.getByRole('dialog', { name: 'Getting started tour' })
  if (await tour.isVisible().catch(() => false)) await tour.getByRole('button', { name: 'Skip tour' }).click()
  const states = Array.from({ length: 200 }, (_, index) => ({ id: `q${index}`, label: `state ${index}`, isStart: index === 0, isAccepting: index === 199, x: (index % 20) * 150, y: Math.floor(index / 20) * 110 }))
  const transitions = states.slice(0, -1).map((state, index) => ({ from: state.id, to: states[index + 1].id, symbols: ['DIGIT'] }))
  const automaton = { type: 'NFA', states, alphabet: ['DIGIT'], transitions }
  await page.locator('.toolbar-actions input[type="file"]').setInputFiles({ name: 'large-automaton.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(automaton)) })
  await expect(page.locator('.builder-footer')).toContainText('200 states', { timeout: 10_000 })
  await expect(page.getByRole('button', { name: 'Simulator', exact: true }).last()).toBeEnabled()
})
