import { chromium } from 'playwright'
import path from 'path'

const consoleErrors = []
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } })
page.on('console', (msg) => {
  if (msg.type() === 'error') consoleErrors.push(msg.text())
})
page.on('pageerror', (err) => consoleErrors.push('pageerror: ' + err.message))

await page.goto('http://localhost:5173')
await page.screenshot({ path: 'verify_1_initial.png' })

const fileInput = await page.locator('input[type=file]')
await fileInput.setInputFiles(path.resolve('../backend/test_drawing.png'))
await page.waitForSelector('canvas.lasso-canvas')
await page.screenshot({ path: 'verify_2_uploaded.png' })

const canvas = await page.locator('canvas.lasso-canvas')
const box = await canvas.boundingBox()
// lasso a rough polygon around the rectangle+circle region of the test drawing
const cx = box.x, cy = box.y
await page.mouse.move(cx + 40, cy + 40)
await page.mouse.down()
await page.mouse.move(cx + 300, cy + 40, { steps: 5 })
await page.mouse.move(cx + 300, cy + 260, { steps: 5 })
await page.mouse.move(cx + 40, cy + 260, { steps: 5 })
await page.mouse.move(cx + 40, cy + 40, { steps: 5 })
await page.mouse.up()
await page.screenshot({ path: 'verify_3_lasso.png' })

await page.selectOption('select', 'front')
await page.fill('textarea', 'e2e test view')
await page.click('button:has-text("Save view")')
await page.waitForTimeout(800)
await page.screenshot({ path: 'verify_4_saved.png' })

const viewBtn = await page.locator('.view-btn').first()
const viewBtnVisible = await viewBtn.isVisible()
await viewBtn.click()
await page.waitForTimeout(500)
await page.screenshot({ path: 'verify_5_selected.png' })

await page.click('button:has-text("Run CV extraction")')
await page.waitForTimeout(1500)
await page.screenshot({ path: 'verify_6_extracted.png' })

const overlayLines = await page.locator('.overlay-svg line, .overlay-svg circle').count()

await page.click('label.toggle:has-text("View raw IR")')
await page.waitForTimeout(300)
await page.screenshot({ path: 'verify_7_rawir.png' })
const rawIrVisible = await page.locator('.raw-ir').isVisible()
const rawIrText = rawIrVisible ? await page.locator('.raw-ir').innerText() : null

console.log(JSON.stringify({
  viewBtnVisible,
  overlayLines,
  rawIrVisible,
  rawIrSnippet: rawIrText ? rawIrText.slice(0, 300) : null,
  consoleErrors,
}, null, 2))

await browser.close()
