import {
  makeCancelSignal,
  renderMedia,
  selectComposition,
} from "@remotion/renderer";
import { randomUUID } from "node:crypto";
import path from "node:path";

interface JobData {
  compositionId: string;
  inputProps: Record<string, unknown>;
}

type JobState =
  | {
      status: "queued";
      data: JobData;
      cancel: () => void;
    }
  | {
      status: "in-progress";
      progress: number;
      data: JobData;
      cancel: () => void;
    }
  | {
      status: "completed";
      videoUrl: string;
      data: JobData;
    }
  | {
      status: "failed";
      error: string;
      data: JobData;
    };

export const makeRenderQueue = ({
  port,
  serveUrl,
  rendersDir,
  chromiumExecutable,
}: {
  port: number;
  serveUrl: string;
  rendersDir: string;
  chromiumExecutable?: string;
}) => {
  const jobs = new Map<string, JobState>();
  let queue: Promise<unknown> = Promise.resolve();

  const processRender = async (jobId: string) => {
    const job = jobs.get(jobId);
    if (!job) throw new Error(`Render job ${jobId} not found`);

    const { cancel, cancelSignal } = makeCancelSignal();

    jobs.set(jobId, {
      progress: 0,
      status: "in-progress",
      cancel,
      data: job.data,
    });

    try {
      const { compositionId, inputProps } = job.data;

      const composition = await selectComposition({
        serveUrl,
        id: compositionId,
        inputProps,
        // ARM64: use system Chromium if configured
        ...(chromiumExecutable ? { chromiumExecutable } : {}),
      });

      await renderMedia({
        cancelSignal,
        serveUrl,
        composition,
        inputProps,
        codec: "h264",
        // ARM64: use system Chromium if configured
        ...(chromiumExecutable ? { chromiumExecutable } : {}),
        // Disable sandbox for Docker (needed for root/headless)
        chromiumOptions: {
          disableWebSecurity: false,
          gl: "angle",
          userAgent: undefined,
          ignoreCertificateErrors: false,
          headless: true,
        },
        onProgress: (progress) => {
          console.info(`${jobId} progress: ${Math.round(progress.progress * 100)}%`);
          jobs.set(jobId, {
            progress: progress.progress,
            status: "in-progress",
            cancel,
            data: job.data,
          });
        },
        outputLocation: path.join(rendersDir, `${jobId}.mp4`),
      });

      jobs.set(jobId, {
        status: "completed",
        videoUrl: `http://localhost:${port}/renders/${jobId}.mp4`,
        data: job.data,
      });
    } catch (error) {
      console.error(`Render ${jobId} failed:`, error);
      jobs.set(jobId, {
        status: "failed",
        error: (error as Error).message,
        data: job.data,
      });
    }
  };

  const queueRender = ({ jobId, data }: { jobId: string; data: JobData }) => {
    jobs.set(jobId, {
      status: "queued",
      data,
      cancel: () => {
        jobs.delete(jobId);
      },
    });
    queue = queue.then(() => processRender(jobId));
  };

  function createJob(data: JobData) {
    const jobId = randomUUID();
    queueRender({ jobId, data });
    return jobId;
  }

  return { createJob, jobs };
};
