import { writeFile } from 'node:fs/promises'

const browserPort = process.env.SAHAYI_CDP_PORT ?? '9222'
const appUrl = process.env.SAHAYI_BROWSER_URL ?? 'http://127.0.0.1:18080'
const outputDir = process.env.SAHAYI_SCREENSHOT_DIR ?? '/tmp/sahayi-browser'
const targets = await (await fetch(`http://127.0.0.1:${browserPort}/json/list`)).json()
const target = targets.find(item => item.type === 'page')
if (!target) throw new Error('No browser page target')

const socket = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject })
let nextId = 1
const pending = new Map()
socket.onmessage = event => {
  const message = JSON.parse(event.data)
  if (!message.id) return
  const waiter = pending.get(message.id)
  if (!waiter) return
  pending.delete(message.id)
  if (message.error) waiter.reject(new Error(message.error.message))
  else waiter.resolve(message.result)
}
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const id = nextId++
  pending.set(id, { resolve, reject })
  socket.send(JSON.stringify({ id, method, params }))
})
const evaluate = async expression => {
  const result = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text)
  return result.result.value
}
const delay = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds))
const waitFor = async (expression, attempts = 80) => {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    if (await evaluate(expression)) return
    await delay(100)
  }
  throw new Error(`Timed out: ${expression}`)
}
const viewport = async (width, height = 900) => {
  await send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: width < 700 })
  await delay(100)
  const fits = await evaluate('document.documentElement.scrollWidth <= window.innerWidth')
  if (!fits) throw new Error(`Horizontal overflow at ${width}px`)
}
const screenshot = async name => {
  const { data } = await send('Page.captureScreenshot', { format: 'png', fromSurface: true, captureBeyondViewport: false })
  await writeFile(`${outputDir}/${name}.png`, Buffer.from(data, 'base64'))
}
const clickText = async text => {
  const clicked = await evaluate(`(() => { const button = [...document.querySelectorAll('button')].find(item => item.textContent.trim() === ${JSON.stringify(text)}); if (!button) return false; button.click(); return true })()`)
  if (!clicked) throw new Error(`Missing button: ${text}`)
}
const clickWhilePresent = async text => {
  for (let step = 0; step < 30; step += 1) {
    const clicked = await evaluate(`(() => { const button = [...document.querySelectorAll('button')].find(item => item.textContent.trim() === ${JSON.stringify(text)}); if (!button) return false; button.click(); return true })()`)
    if (!clicked) return step
    await delay(50)
  }
  throw new Error(`Too many progressive fields: ${text}`)
}
const setLocale = async locale => evaluate(`(() => { const select = document.querySelector('#language-selector'); select.value = ${JSON.stringify(locale)}; select.dispatchEvent(new Event('change', { bubbles: true })); return true })()`)
const intentTimings = []

await send('Page.enable')
await send('Runtime.enable')
await send('Page.navigate', { url: 'about:blank' })
await delay(200)
await send('Page.navigate', { url: appUrl })
await delay(500)
await waitFor(`document.querySelector('h1')?.textContent === 'Sahayi'`)
await viewport(360, 800)
await screenshot('welcome-en-360')
await setLocale('hi')
await waitFor(`document.documentElement.lang === 'hi'`)
await viewport(390, 844)
await screenshot('welcome-hi-390')
await setLocale('ml')
await waitFor(`document.documentElement.lang === 'ml'`)
await viewport(768, 900)
await screenshot('welcome-ml-768')
await setLocale('en')
await waitFor(`document.documentElement.lang === 'en'`)

await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Tab', code: 'Tab' })
await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Tab', code: 'Tab' })
const focus = await evaluate(`(() => { const element = document.activeElement; const style = getComputedStyle(element); return { tag: element.tagName, outline: style.outlineStyle, width: style.outlineWidth } })()`)
if (focus.outline === 'none' || focus.width === '0px') throw new Error('Visible keyboard focus is missing')
await screenshot('keyboard-focus-768')

const localIntentJourney = async ({ locale, start, find, confirm, end, query, localText, widths, name }) => {
  await setLocale(locale)
  await waitFor(`document.documentElement.lang === ${JSON.stringify(locale)}`)
  await clickText(start)
  await waitFor(`Boolean(document.querySelector('textarea#service-query')) && document.querySelectorAll('.service-card').length === 0 && !document.querySelector('.citizen-progress')`)
  await evaluate(`performance.clearResourceTimings()`)
  await evaluate(`(() => { const input = document.querySelector('textarea#service-query'); const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set; setter.call(input, ${JSON.stringify(query)}); input.dispatchEvent(new Event('input', { bubbles: true })); return true })()`)
  const timing = await evaluate(`(() => { const button = [...document.querySelectorAll('button')].find(item => item.textContent.trim() === ${JSON.stringify(find)}); const started = performance.now(); button.click(); return performance.now() - started })()`)
  intentTimings.push({ locale, milliseconds: timing })
  await waitFor(`document.body.textContent.includes(${JSON.stringify(localText)}) && Boolean(document.querySelector('.suggested-responses button'))`)
  if (await evaluate(`Boolean(document.querySelector('.trust-card'))`)) throw new Error(`Intent service opened without confirmation: ${locale}`)
  if (await evaluate(`performance.getEntriesByType('resource').length !== 0`)) throw new Error(`Local intent caused a network request: ${locale}`)
  for (const width of widths) {
    await viewport(width, width < 700 ? 844 : 900)
    await screenshot(`${name}-${width}`)
  }
  await clickText(confirm)
  await waitFor(`Boolean(document.querySelector('.conversation-question'))`)
  if (!await evaluate(`document.querySelector('h1')?.textContent === ${JSON.stringify(locale === 'en' ? 'What do you need help with?' : locale === 'hi' ? 'आपको किस काम में मदद चाहिए?' : 'നിങ്ങൾക്ക് എന്ത് സഹായമാണ് വേണ്ടത്?')}`)) throw new Error(`Conversation surface changed during readiness: ${locale}`)
  await clickText(end)
  await waitFor(`document.querySelector('h1')?.textContent === 'Sahayi'`)
}

await localIntentJourney({ locale: 'en', start: 'Start', find: 'Send', confirm: 'Yes, continue', end: 'End session', query: 'need aadhaar adress updation after moving', localText: 'Matched on this device.', widths: [360, 1280], name: 'intent-aadhaar-en' })
await localIntentJourney({ locale: 'hi', start: 'शुरू करें', find: 'भेजें', confirm: 'हाँ, आगे बढ़ें', end: 'सत्र समाप्त करें', query: 'आधार का पत्ता अप्डेट करना है', localText: 'इस डिवाइस पर मिलान हुआ।', widths: [390], name: 'intent-aadhaar-hi' })
await localIntentJourney({ locale: 'ml', start: 'തുടങ്ങുക', find: 'അയയ്ക്കുക', confirm: 'അതെ, തുടരുക', end: 'സെഷൻ അവസാനിപ്പിക്കുക', query: 'old age പെൻഷൻ kerala അപേക്ഷ', localText: 'ഈ ഉപകരണത്തിൽ പൊരുത്തപ്പെടുത്തി.', widths: [768], name: 'intent-pension-ml' })
await setLocale('en')
await waitFor(`document.documentElement.lang === 'en'`)

await clickText('Start')
await waitFor(`document.querySelector('h1')?.textContent === 'What do you need help with?'`)
await waitFor(`document.body.textContent.includes('Voice is optional.') && document.body.textContent.includes('You can always type instead.')`)
const voiceFallback = await evaluate(`document.body.textContent.includes('Voice is optional.') && document.body.textContent.includes('You can always type instead.')`)
if (!voiceFallback) throw new Error('Voice disclosure and text fallback are missing')
await evaluate(`(() => { const input = document.querySelector('textarea#service-query'); const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set; setter.call(input, 'I need to change my Aadhaar address'); input.dispatchEvent(new Event('input', { bubbles: true })); return true })()`)
await clickText('Send')
await waitFor(`document.body.textContent.includes('Is this the service you mean?')`)
await clickText('Yes, continue')
await waitFor(`Boolean(document.querySelector('.conversation-question'))`)
await clickText('Yes')
await waitFor(`document.body.textContent.includes('Which official address-update route do you intend to use?')`)
await clickText('My own accepted proof of address')
await waitFor(`document.body.textContent.includes("Do you have a proof-of-address document that appears in UIDAI's accepted-document guidance")`)
const initialOcrAssets = await evaluate(`performance.getEntriesByType('resource').filter(item => item.name.includes('/ocr/') || item.name.includes('documentOcr-')).length`)
if (initialOcrAssets !== 0) throw new Error('OCR loaded before explicit citizen action')
await clickText('Check a document on this device')
await waitFor(`Boolean(document.querySelector('.document-helper input[type="file"]'))`)
await evaluate(`(() => {
  const original = window.fetch.bind(window)
  window.__sahayiRecordedFetches = []
  window.fetch = (input, init) => {
    window.__sahayiRecordedFetches.push({ url: String(input), body: typeof init?.body === 'string' ? init.body : '' })
    return original(input, init)
  }
  const canvas = document.createElement('canvas')
  canvas.width = 1400
  canvas.height = 260
  const context = canvas.getContext('2d')
  context.fillStyle = 'white'
  context.fillRect(0, 0, canvas.width, canvas.height)
  context.fillStyle = 'black'
  context.font = '52px sans-serif'
  context.fillText('Valid proof of address', 50, 100)
  context.fillText('Accepted proof address guidance', 50, 190)
  return new Promise(resolve => canvas.toBlob(blob => {
    const transfer = new DataTransfer()
    transfer.items.add(new File([blob], 'synthetic-local.png', { type: 'image/png' }))
    const input = document.querySelector('.document-helper input[type="file"]')
    input.files = transfer.files
    input.dispatchEvent(new Event('change', { bubbles: true }))
    canvas.width = 1
    canvas.height = 1
    resolve(true)
  }, 'image/png'))
})()`)
await waitFor(`document.body.textContent.includes('appears to contain information relevant')`, 800)
if (await evaluate(`document.body.textContent.includes('synthetic-local.png')`)) throw new Error('Document filename was rendered')
const ocrApiCallsBeforeConfirm = await evaluate(`window.__sahayiRecordedFetches.filter(item => item.url.includes('/api/')).length`)
if (ocrApiCallsBeforeConfirm !== 0) throw new Error('Local OCR sent a backend request before confirmation')
const remoteOcrAssets = await evaluate(`performance.getEntriesByType('resource').filter(item => (item.name.includes('/ocr/') || item.name.includes('documentOcr-')) && !item.name.startsWith(location.origin)).map(item => item.name)`)
if (remoteOcrAssets.length) throw new Error('OCR loaded a cross-origin runtime asset')
await clickText('Confirm this clue')
await waitFor(`document.body.textContent.includes('Confirmed as an unverified preparation clue.')`)
const ocrRequestBodies = await evaluate(`window.__sahayiRecordedFetches.filter(item => item.url.includes('/api/')).map(item => item.body)`)
if (ocrRequestBodies.length !== 1 || ocrRequestBodies.some(body => body.includes('Valid proof') || body.includes('synthetic-local') || !body.includes('document_evidence'))) throw new Error('Confirmed OCR evidence crossed the bounded API contract')
await viewport(360, 800)
await screenshot('ocr-helper-en-360')
await clickText('Yes')
await waitFor(`document.body.textContent.includes('What new address should your preparation sheet show?') && Boolean(document.querySelector('#preparation-value'))`)
if (await evaluate(`Boolean(document.querySelector('.conversation-composer'))`)) throw new Error('A second composer remained during a preparation question')
await evaluate(`(() => { const input = document.querySelector('#preparation-value'); const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set; setter.call(input, 'DEMO locality, Bengaluru, Karnataka'); input.dispatchEvent(new Event('input', { bubbles: true })); return true })()`)
await clickText('Confirm and continue')
await waitFor(`Boolean(document.querySelector('.conversation-result')) && Boolean(document.querySelector('.prepared-guidance')) && Boolean(document.querySelector('.official-ready a')) && document.body.textContent.includes('DEMO locality, Bengaluru, Karnataka')`)
const fieldRequestBodies = await evaluate(`window.__sahayiRecordedFetches.filter(item => item.url.includes('/api/')).map(item => item.body)`)
if (fieldRequestBodies.some(body => body.includes('DEMO locality') || body.includes('Valid proof of address'))) throw new Error('A personal preparation value crossed the API boundary')
await evaluate(`(() => { const details = document.querySelector('.prepared-guidance'); details.open = true; details.scrollIntoView({ block: 'start' }); return true })()`)
await clickText('Edit answer')
await evaluate(`(() => { const input = document.querySelector('[id^="edit-"]'); const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; setter.call(input, 'EDITED DEMO locality, Bengaluru'); input.dispatchEvent(new Event('input', { bubbles: true })); return true })()`)
await clickText('Save edit')
await waitFor(`document.body.textContent.includes('EDITED DEMO locality, Bengaluru')`)
await viewport(360, 800)
await screenshot('unified-complete-en-360')
await viewport(1280, 900)
await screenshot('unified-complete-en-1280')
await clickText('End session')
await waitFor(`document.querySelector('h1')?.textContent === 'Sahayi'`)
await clickText('Start')
await waitFor(`document.querySelector('h1')?.textContent === 'What do you need help with?'`)
await clickText('Browse all services')
await waitFor(`document.querySelector('h1')?.textContent === 'Supported services' && document.querySelectorAll('.service-card').length > 0`)
await viewport(1280, 900)
await screenshot('catalogue-en-desktop')
if (!await evaluate(`(() => { const button = [...document.querySelectorAll('.service-card')].find(item => item.textContent.includes('Update your Aadhaar address online')); if (!button) return false; button.click(); return true })()`)) throw new Error('Aadhaar service card is missing')
await waitFor(`document.querySelector('h1')?.textContent === 'Update your Aadhaar address online'`)
if (!await evaluate(`document.body.textContent.includes('Your Sahayi journey') && document.body.textContent.includes('Procedure Intelligence demonstration')`)) throw new Error('Unified journey or Procedure Intelligence is missing')
await screenshot('aadhaar-detail-en-desktop')
await clickText('Build personalized checklist')
await waitFor(`document.querySelector('h1')?.textContent === 'Personalized preparation checklist'`)
await viewport(390, 844)
await screenshot('checklist-en-390')
await clickText('Prepare synthetic demo worksheet')
await waitFor(`document.querySelector('.watermark')?.textContent.trim() === 'DEMO — NOT FOR SUBMISSION'`)
await viewport(360, 800)
await clickWhilePresent('Next demo field')
const privateBlank = await evaluate(`[...document.querySelectorAll('.worksheet-fields dd')].some(item => item.textContent.includes('not collected') && item.textContent.includes('—'))`)
if (!privateBlank) throw new Error('Private worksheet field is not visibly blank')
await screenshot('synthetic-form-en-360')
await clickText('Continue with demo submission')
await waitFor(`document.querySelector('h1')?.textContent === 'Demo submission and status'`)
const disclosure = await evaluate(`document.body.textContent.includes('No application will be submitted.') && document.body.textContent.includes('No government system will be contacted.')`)
if (!disclosure) throw new Error('Demo disclosure is incomplete')
await clickText('Action-required scenario')
await waitFor(`document.body.textContent.includes('DEMO-UIDAI-ACTION')`)
const currentStep = await evaluate(`document.querySelector('[aria-current="step"] h2')?.textContent`)
if (currentStep !== 'Preparation completed') throw new Error('Accessible current demo status is missing')
await viewport(390, 844)
await screenshot('demo-status-en-390')
const trust = await evaluate(`(() => { const details = document.querySelector('.trust-explanation'); details.open = true; details.scrollIntoView({ block: 'center' }); return details.textContent.includes('never silently replaced') })()`)
if (!trust) throw new Error('Trust explanation is incomplete')
await viewport(768, 900)
await screenshot('trust-explanation-en-768')
await clickText('End session')
await waitFor(`document.querySelector('h1')?.textContent === 'Sahayi' && document.body.textContent.includes('cleared all in-memory session data')`)
if (await evaluate(`document.body.textContent.includes('DEMO-UIDAI-ACTION')`)) throw new Error('End session retained the demo reference')
await screenshot('session-cleared-en-768')

await clickText('Start')
await waitFor(`Boolean(document.querySelector('textarea#service-query'))`)
await clickText('Browse all services')
await waitFor(`document.querySelectorAll('.service-card').length === 2`)
await evaluate(`document.querySelector('.service-card').click()`)
await waitFor(`Boolean(document.querySelector('.trust-card'))`)
await clickText('Ask Sahayi AI')
await waitFor(`document.querySelector('h1')?.textContent === 'Ask Sahayi AI'`)
await viewport(768, 900)
const disabledConsent = await evaluate(`document.querySelector('.consent-choice input')?.disabled === true`)
const publicConfig = await evaluate(`fetch('/api/v1/public-config').then(response => response.json())`)
if (publicConfig.agent_available === disabledConsent) throw new Error('Agent consent state does not match public configuration')
const groqDisclosure = await evaluate(`document.body.textContent.includes('GroqCloud') && document.body.textContent.includes('Groq collects usage metadata') && document.body.textContent.includes('owner-controlled Groq Console setting')`)
if (!groqDisclosure) throw new Error('English GroqCloud disclosure is incomplete')
await screenshot(`agent-${publicConfig.agent_available ? 'enabled' : 'disabled'}-en-768`)
await setLocale('hi')
await waitFor(`document.body.textContent.includes('GroqCloud') && document.body.textContent.includes('Groq Console')`)
await viewport(390, 844)
await screenshot('agent-disabled-hi-390')
await setLocale('ml')
await waitFor(`document.body.textContent.includes('GroqCloud') && document.body.textContent.includes('Groq Console')`)
await viewport(768, 900)
await screenshot('agent-disabled-ml-768')
await setLocale('en')
await clickText('End session')
await waitFor(`document.querySelector('h1')?.textContent === 'Sahayi'`)

const localizedDemo = async ({ locale, start, browse, form, demo, end, width, name }) => {
  await setLocale(locale)
  await waitFor(`document.documentElement.lang === ${JSON.stringify(locale)}`)
  await clickText(start)
  await waitFor(`Boolean(document.querySelector('textarea#service-query'))`)
  await clickText(browse)
  await waitFor(`document.querySelectorAll('.service-card').length === 2`)
  await evaluate(`(() => { const cards = document.querySelectorAll('.service-card'); cards[cards.length - 1].click(); return true })()`)
  await waitFor(`Boolean(document.querySelector('.trust-card'))`)
  await clickText(form)
  await waitFor(`Boolean(document.querySelector('.watermark'))`)
  await clickWhilePresent(locale === 'hi' ? 'अगला डेमो फ़ील्ड' : 'അടുത്ത ഡെമോ ഫീൽഡ്')
  await clickText(demo)
  await waitFor(`Boolean(document.querySelector('.disclosure-card'))`)
  await viewport(width, width === 390 ? 844 : 900)
  await screenshot(name)
  await clickText(end)
  await waitFor(`document.querySelector('h1')?.textContent === 'Sahayi'`)
}
await localizedDemo({ locale: 'hi', start: 'शुरू करें', browse: 'सभी सेवाएँ देखें', form: 'कृत्रिम डेमो वर्कशीट तैयार करें', demo: 'डेमो जमा करने के साथ आगे बढ़ें', end: 'सत्र समाप्त करें', width: 390, name: 'demo-disclosure-hi-390' })
await localizedDemo({ locale: 'ml', start: 'തുടങ്ങുക', browse: 'എല്ലാ സേവനങ്ങളും കാണുക', form: 'കൃത്രിമ ഡെമോ വർക്ക്‌ഷീറ്റ് തയ്യാറാക്കുക', demo: 'ഡെമോ സമർപ്പണവുമായി തുടരുക', end: 'സെഷൻ അവസാനിപ്പിക്കുക', width: 768, name: 'demo-disclosure-ml-768' })

socket.close()
process.stdout.write(JSON.stringify({ screenshots: 23, widths: [360, 390, 768, 1280], locales: ['en', 'hi', 'ml'], visibleFocus: focus, intentTimings, localIntentNetworkRequests: 0, explicitIntentConfirmation: true, automaticPreparation: true, preparationValueStayedLocal: true, preparedValueEditedLocally: true, structuredQuestionHasSingleComposer: true, ocrLazyLoaded: true, ocrSameOrigin: true, ocrBackendRequestsBeforeConfirmation: 0, ocrConfirmedEvidenceOnly: true, agentAvailable: publicConfig.agent_available, groqDisclosure: true, demoDisclosure: disclosure, currentDemoStep: currentStep, sessionCleared: true }, null, 2) + '\n')
