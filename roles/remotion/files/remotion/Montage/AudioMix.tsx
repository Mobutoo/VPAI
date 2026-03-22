import React from "react";
import { Audio, interpolate, useVideoConfig } from "remotion";
import type { AudioData, SubtitleLine } from "./types";

interface AudioMixProps {
  audio: AudioData;
  subtitles?: SubtitleLine[];
  totalDurationInFrames: number;
  titleOffsetFrames: number;
}

function isVoActiveAtFrame(
  frame: number,
  fps: number,
  subtitles?: SubtitleLine[],
): boolean {
  if (!subtitles || subtitles.length === 0) return false;
  const currentMs = (frame / fps) * 1000;
  return subtitles.some(
    (line) => currentMs >= line.startMs && currentMs <= line.endMs,
  );
}

export const AudioMix: React.FC<AudioMixProps> = ({
  audio,
  subtitles,
  totalDurationInFrames,
  titleOffsetFrames,
}) => {
  const { fps } = useVideoConfig();

  const musicVolumeCallback = (frame: number): number => {
    const { musicVolume, musicFadeInFrames, musicFadeOutFrames, duckMusicOnVo, duckLevel } = audio;

    // Fade in
    if (musicFadeInFrames > 0 && frame < musicFadeInFrames) {
      return interpolate(frame, [0, musicFadeInFrames], [0, musicVolume], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      });
    }

    // Fade out
    const fadeOutStart = totalDurationInFrames - musicFadeOutFrames;
    if (musicFadeOutFrames > 0 && frame > fadeOutStart) {
      return interpolate(
        frame,
        [fadeOutStart, totalDurationInFrames],
        [musicVolume, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
      );
    }

    // Duck during VO (subtract title offset since subtitle timestamps are content-relative)
    if (duckMusicOnVo && isVoActiveAtFrame(frame - titleOffsetFrames, fps, subtitles)) {
      return musicVolume * duckLevel;
    }

    return musicVolume;
  };

  return (
    <>
      {audio.musicSrc && (
        <Audio src={audio.musicSrc} volume={musicVolumeCallback} />
      )}
      {audio.voiceoverSrc && (
        <Audio src={audio.voiceoverSrc} volume={audio.voiceoverVolume} />
      )}
    </>
  );
};
