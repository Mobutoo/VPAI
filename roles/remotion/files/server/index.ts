import express, { NextFunction, Request, Response } from "express";
import { makeRenderQueue } from "./render-queue";
import { bundle } from "@remotion/bundler";
import path from "node:path";
import { ensureBrowser } from "@remotion/renderer";
import { z } from "zod";

const {
  PORT = 3200,
  REMOTION_SERVE_URL,
  CHROME_EXECUTABLE_PATH,
  REMOTION_API_TOKEN,
  REMOTION_PUBLIC_URL,
} = process.env;

// Maximum queued + in-progress jobs before returning 429
const MAX_QUEUE_DEPTH = 10;

// Allowlist of registered composition IDs
const KNOWN_COMPOSITIONS = new Set(["HelloWorld"]);

const RenderRequestSchema = z.object({
  compositionId: z.string().optional(),
  inputProps: z.record(z.unknown()).optional(),
});

// Auth middleware — no-op when token is not configured
function requireAuth(req: Request, res: Response, next: NextFunction): void {
  if (!REMOTION_API_TOKEN) {
    next();
    return;
  }
  const header = req.headers.authorization ?? "";
  const token = header.startsWith("Bearer ") ? header.slice(7) : "";
  if (token !== REMOTION_API_TOKEN) {
    res.status(401).json({ message: "Unauthorized" });
    return;
  }
  next();
}

function setupApp({ remotionBundleUrl }: { remotionBundleUrl: string }) {
  const app = express();

  const rendersDir = path.resolve("renders");

  const queue = makeRenderQueue({
    port: Number(PORT),
    serveUrl: remotionBundleUrl,
    rendersDir,
    chromiumExecutable: CHROME_EXECUTABLE_PATH,
    publicBaseUrl: REMOTION_PUBLIC_URL,
  });

  // Host renders on /renders
  app.use("/renders", express.static(rendersDir));
  app.use(express.json());

  // Root — API info (unauthenticated)
  app.get("/", (_req, res) => {
    res.json({
      service: "Remotion Render Server",
      status: "ok",
      endpoints: {
        health: "GET /health",
        createRender: "POST /renders",
        getJob: "GET /renders/:jobId",
        cancelJob: "DELETE /renders/:jobId",
      },
    });
  });

  // Health check — unauthenticated
  app.get("/health", (_req, res) => {
    res.json({ status: "ok", renders: queue.jobs.size });
  });

  // Endpoint to create a new render job
  app.post("/renders", requireAuth, (req, res) => {
    // Queue depth cap — prevent resource exhaustion
    const active = [...queue.jobs.values()].filter(
      (j) => j.status === "queued" || j.status === "in-progress",
    ).length;
    if (active >= MAX_QUEUE_DEPTH) {
      res.status(429).json({ message: "Queue full, try again later" });
      return;
    }

    const parsed = RenderRequestSchema.safeParse(req.body ?? {});
    if (!parsed.success) {
      res.status(400).json({ message: "Invalid request body", errors: parsed.error.issues });
      return;
    }

    const compositionId = parsed.data.compositionId ?? "HelloWorld";

    if (!KNOWN_COMPOSITIONS.has(compositionId)) {
      res.status(400).json({ message: "Unknown composition" });
      return;
    }

    const jobId = queue.createJob({
      compositionId,
      inputProps: parsed.data.inputProps ?? {},
    });
    res.json({ jobId });
  });

  // Endpoint to get a job status
  app.get("/renders/:jobId", requireAuth, (req, res) => {
    const job = queue.jobs.get(req.params.jobId);
    if (!job) {
      res.status(404).json({ message: "Job not found" });
      return;
    }
    res.json(job);
  });

  // Endpoint to cancel a job
  app.delete("/renders/:jobId", requireAuth, (req, res) => {
    const job = queue.jobs.get(req.params.jobId);
    if (!job) {
      res.status(404).json({ message: "Job not found" });
      return;
    }
    if (job.status !== "queued" && job.status !== "in-progress") {
      res.status(400).json({ message: "Job is not cancellable" });
      return;
    }
    job.cancel();
    res.json({ message: "Job cancelled" });
  });

  return app;
}

async function main() {
  // ARM64: use system Chromium if CHROME_EXECUTABLE_PATH is set
  if (CHROME_EXECUTABLE_PATH) {
    console.info(`Using system Chromium: ${CHROME_EXECUTABLE_PATH}`);
  } else {
    // Download Remotion-managed browser if no system browser configured
    await ensureBrowser();
  }

  const remotionBundleUrl = REMOTION_SERVE_URL
    ? path.resolve(REMOTION_SERVE_URL)
    : await bundle({
        entryPoint: path.resolve("remotion/index.ts"),
        onProgress(progress) {
          console.info(`Bundling Remotion project: ${progress}%`);
        },
      });

  const app = setupApp({ remotionBundleUrl });

  app.listen(PORT, () => {
    console.info(`Remotion render server listening on port ${PORT}`);
  });
}

main().catch(console.error);
