'use strict'
/**
 * wizy — GrapeJS editor API server
 * Endpoints:
 *   GET  /api/events  — SSE stream (browser subscribes)
 *   POST /api/html    — Claude/API pushes HTML → broadcasts to all open browsers
 *   PUT  /api/html    — Browser saves current editor state (no broadcast)
 *   GET  /api/html    — Claude/API retrieves current HTML + CSS
 */

const express = require('express')
const path    = require('path')

const app = express()
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
  // Send current state immediately so late-joiners see existing content
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

app.listen(80, () => console.log('[wizy] ready on :80'))
