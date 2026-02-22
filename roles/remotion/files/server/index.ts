import express from "express";
import { makeRenderQueue } from "./render-queue";
import { bundle } from "@remotion/bundler";
import path from "node:path";
import { ensureBrowser } from "@remotion/renderer";

const { PORT = 3200, REMOTION_SERVE_URL, CHROME_EXECUTABLE_PATH } = process.env;

function setupApp({ remotionBundleUrl }: { remotionBundleUrl: string }) {
  const app = express();

  const rendersDir = path.resolve("renders");

  const queue = makeRenderQueue({
    port: Number(PORT),
    serveUrl: remotionBundleUrl,
    rendersDir,
    chromiumExecutable: CHROME_EXECUTABLE_PATH,
  });

  // Host renders on /renders
  app.use("/renders", express.static(rendersDir));
  app.use(express.json());

  // Health check
  app.get("/health", (_req, res) => {
    res.json({ status: "ok", renders: queue.jobs.size });
  });

  // Endpoint to create a new render job
  app.post("/renders", async (req, res) => {
    const { compositionId, inputProps } = req.body || {};
    const jobId = queue.createJob({
      compositionId: compositionId || "HelloWorld",
      inputProps: inputProps || {},
    });
    res.json({ jobId });
  });

  // Endpoint to get a job status
  app.get("/renders/:jobId", (req, res) => {
    const jobId = req.params.jobId;
    const job = queue.jobs.get(jobId);
    if (!job) {
      res.status(404).json({ message: "Job not found" });
      return;
    }
    res.json(job);
  });

  // Endpoint to cancel a job
  app.delete("/renders/:jobId", (req, res) => {
    const jobId = req.params.jobId;
    const job = queue.jobs.get(jobId);
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
