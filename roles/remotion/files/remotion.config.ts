import { Config } from "@remotion/cli/config";

// ARM64 (Raspberry Pi 5): use angle renderer (swangle = software WebGL fallback)
Config.setChromiumOpenGlRenderer("angle");
Config.setDelayRenderTimeoutInMilliseconds(120000);
Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
