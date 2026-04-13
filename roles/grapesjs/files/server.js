'use strict'
/**
 * wizy — GrapeJS editor API server
 * Endpoints:
 *   GET  /api/events  — SSE stream (browser subscribes)
 *   POST /api/html    — Claude/API pushes HTML → broadcasts to all open browsers
 *   PUT  /api/html    — Browser saves current editor state (no broadcast)
 *   GET  /api/html    — Claude/API retrieves current HTML + CSS
 *   POST /api/docx    — Upload .docx → Mammoth converts → broadcast to browsers
 */

const express  = require('express')
const path     = require('path')
const multer   = require('multer')
const mammoth  = require('mammoth')
const JSZip    = require('jszip')

const app    = express()
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 20 * 1024 * 1024 } })

app.use(express.json({ limit: '10mb' }))
app.use(express.static(path.join(__dirname, 'public')))

// In-memory state — survives browser closes, reset on container restart
let state = { html: '', css: '' }
const clients = new Set()

function broadcast (payload) {
  const data = `data: ${JSON.stringify(payload)}\n\n`
  for (const res of clients) res.write(data)
}

/* ── SSE stream ─────────────────────────────────────────── */
app.get('/api/events', (req, res) => {
  res.setHeader('Content-Type',  'text/event-stream')
  res.setHeader('Cache-Control', 'no-cache')
  res.setHeader('Connection',    'keep-alive')
  res.flushHeaders()
  res.write(`data: ${JSON.stringify({ type: 'init', html: state.html, css: state.css })}\n\n`)
  clients.add(res)
  req.on('close', () => clients.delete(res))
})

/* ── Claude/API → push HTML to all open browsers ───────── */
app.post('/api/html', (req, res) => {
  const { html, css = '' } = req.body
  if (typeof html !== 'string') {
    return res.status(400).json({ error: 'body.html (string) required' })
  }
  state = { html, css }
  broadcast({ type: 'load', html, css })
  res.json({ ok: true, clients: clients.size })
})

/* ── Browser → save current editor state ───────────────── */
app.put('/api/html', (req, res) => {
  const { html, css = '' } = req.body
  if (typeof html !== 'string') {
    return res.status(400).json({ error: 'body.html (string) required' })
  }
  state = { html, css }
  res.json({ ok: true })
})

/* ── Claude/API → retrieve current HTML ────────────────── */
app.get('/api/html', (_req, res) => {
  res.json(state)
})

/* ── Pre-process DOCX: replace Word page breaks with marker ── */
const PAGE_BREAK_MARKER = '__WIZY_PAGE_BREAK__'
const PAGE_BREAK_XML    = `<w:p><w:pPr/><w:r><w:t xml:space="preserve">${PAGE_BREAK_MARKER}</w:t></w:r></w:p>`
const PAGE_BREAK_HTML   = '<div class="wizy-page-break" style="page-break-after:always;border-top:2px dashed #bbb;margin:24px 0 16px;padding-bottom:8px;text-align:center"><span style="font-size:10px;color:#aaa;font-style:italic">— Saut de page —</span></div>'

async function preprocessDocx (buffer) {
  const zip = await JSZip.loadAsync(buffer)
  const docFile = zip.file('word/document.xml')
  if (!docFile) return buffer
  let xml = await docFile.async('string')
  xml = xml.replace(/<w:br\s+w:type="page"\s*\/>/g, PAGE_BREAK_XML)
  zip.file('word/document.xml', xml)
  return zip.generateAsync({ type: 'nodebuffer' })
}

/* ── Upload .docx → Mammoth → broadcast ────────────────── */
app.post('/api/docx', upload.single('file'), async (req, res) => {
  if (!req.file) {
    return res.status(400).json({ error: 'file (multipart/form-data) required' })
  }
  try {
    const processed = await preprocessDocx(req.file.buffer)
    const result    = await mammoth.convertToHtml({ buffer: processed })
    const html      = result.value.replace(
      new RegExp(`<p[^>]*>${PAGE_BREAK_MARKER}<\\/p>`, 'g'),
      PAGE_BREAK_HTML
    )
    state = { html, css: '' }
    broadcast({ type: 'load', html, css: '' })
    res.json({ ok: true, clients: clients.size, warnings: result.messages.length })
  } catch (err) {
    res.status(500).json({ error: err.message })
  }
})

app.listen(80, () => console.log('[wizy] ready on :80'))
