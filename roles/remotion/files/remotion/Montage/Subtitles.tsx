import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import type { SubtitleLine, ArtisticDirection } from "./types";

interface SubtitlesProps {
  lines: SubtitleLine[];
  style: ArtisticDirection["subtitleStyle"];
  typography: ArtisticDirection["typography"];
  offsetFrames: number;
}

function getActiveSubtitle(
  lines: SubtitleLine[],
  frame: number,
  fps: number,
  offsetFrames: number,
): SubtitleLine | null {
  const currentMs = ((frame - offsetFrames) / fps) * 1000;
  for (const line of lines) {
    if (currentMs >= line.startMs && currentMs <= line.endMs) {
      return line;
    }
  }
  return null;
}

const STYLE_CONFIG: Record<
  ArtisticDirection["subtitleStyle"],
  {
    fontSize: number;
    position: "center" | "bottom" | "bottom-left";
    background: boolean;
    bold: boolean;
  }
> = {
  reel: { fontSize: 48, position: "center", background: false, bold: true },
  cinema: { fontSize: 28, position: "bottom", background: true, bold: false },
  minimal: {
    fontSize: 20,
    position: "bottom-left",
    background: false,
    bold: false,
  },
  "bold-center": {
    fontSize: 56,
    position: "center",
    background: false,
    bold: true,
  },
  karaoke: { fontSize: 42, position: "center", background: false, bold: true },
};

export const Subtitles: React.FC<SubtitlesProps> = ({
  lines,
  style,
  typography,
  offsetFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const active = getActiveSubtitle(lines, frame, fps, offsetFrames);
  if (!active) return null;

  const config = STYLE_CONFIG[style];

  const containerStyle: React.CSSProperties = {
    position: "absolute",
    left: 0,
    right: 0,
    display: "flex",
    justifyContent:
      config.position === "bottom-left" ? "flex-start" : "center",
    pointerEvents: "none",
  };

  if (config.position === "center") {
    Object.assign(containerStyle, {
      top: 0,
      bottom: 0,
      alignItems: "center",
    });
  } else if (config.position === "bottom") {
    Object.assign(containerStyle, { bottom: "10%" });
  } else {
    Object.assign(containerStyle, { bottom: "8%", paddingLeft: 40 });
  }

  const textStyle: React.CSSProperties = {
    fontSize: config.fontSize,
    fontWeight: config.bold ? "bold" : "normal",
    color: typography.textColor,
    fontFamily: typography.fontFamily,
    textAlign: "center",
    maxWidth: "80%",
    lineHeight: 1.3,
    textShadow: config.background
      ? "none"
      : "2px 2px 6px rgba(0,0,0,0.8), 0 0 20px rgba(0,0,0,0.5)",
    ...(config.background && {
      backgroundColor: "rgba(0,0,0,0.6)",
      padding: "8px 20px",
      borderRadius: 4,
    }),
  };

  return (
    <AbsoluteFill>
      <div style={containerStyle}>
        <div style={textStyle}>{active.text}</div>
      </div>
    </AbsoluteFill>
  );
};
