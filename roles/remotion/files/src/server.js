import express from 'express';
import { renderMedia, selectComposition } from '@remotion/renderer';
import { bundle } from '@remotion/bundler';
import { v4 as uuidv4 } from 'uuid';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
app.use(express.json());

const PORT = process.env.PORT || 3200;
const API_TOKEN = process.env.REMOTION_API_TOKEN || '';
const OUTPUT_DIR = '/app/output';

// In-flight renders
const renders = new Map();

// Auth middleware
const auth = (req, res, next) => {
  if (!API_TOKEN) return next();
  const token = req.headers.authorization?.replace('Bearer ', '');
  if (token !== API_TOKEN) return res.status(401).json({ error: 'Unauthorized' });
  next();
};

// Health check
app.get('/health', (_req, res) => {
  res.json({ status: 'ok', renders: renders.size });
});

// Start render
app.post('/render', auth, async (req, res) => {
  const { compositionId, inputProps, codec, outputFormat } = req.body;
  const id = uuidv4();

  renders.set(id, { status: 'pending', progress: 0, startedAt: Date.now() });

  // Start render in background
  (async () => {
    try {
      renders.set(id, { ...renders.get(id), status: 'rendering' });

      const bundled = await bundle({
        entryPoint: path.resolve(__dirname, 'compositions/index.js'),
        enableMultiProcessOnLinux: true,
      });

      const composition = await selectComposition({
        serveUrl: bundled,
        id: compositionId || 'ProductDemo',
        inputProps: inputProps || {},
      });

      const outputPath = path.join(OUTPUT_DIR, `${id}.${outputFormat || 'mp4'}`);

      await renderMedia({
        composition,
        serveUrl: bundled,
        codec: codec || 'h264',
        outputLocation: outputPath,
        inputProps: inputProps || {},
        onProgress: ({ progress }) => {
          renders.set(id, { ...renders.get(id), progress });
        },
      });

      renders.set(id, {
        ...renders.get(id),
        status: 'done',
        progress: 1,
        outputPath,
        completedAt: Date.now(),
      });
    } catch (err) {
      renders.set(id, {
        ...renders.get(id),
        status: 'error',
        error: err.message,
        completedAt: Date.now(),
      });
    }
  })();

  res.json({ id, status: 'pending' });
});

// Get render status
app.get('/status/:id', auth, (req, res) => {
  const render = renders.get(req.params.id);
  if (!render) return res.status(404).json({ error: 'Not found' });
  res.json({ id: req.params.id, ...render });
});

// Get render output
app.get('/output/:id', auth, (req, res) => {
  const render = renders.get(req.params.id);
  if (!render || render.status !== 'done') {
    return res.status(404).json({ error: 'Not ready' });
  }
  res.sendFile(render.outputPath);
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`Remotion server listening on port ${PORT}`);
});
