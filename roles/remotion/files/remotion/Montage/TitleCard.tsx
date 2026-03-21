import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { TitleData, ArtisticDirection } from "./types";

interface TitleCardProps extends TitleData {
  typography: ArtisticDirection["typography"];
}

export const TitleCard: React.FC<TitleCardProps> = ({
  text,
  subtitle,
  color,
  backgroundColor,
  durationInFrames,
  animation,
  typography,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const fadeIn = interpolate(frame, [0, 30], [0, 1], {
    extrapolateRight: "clamp",
  });
  const fadeOut = interpolate(
    frame,
    [durationInFrames - 20, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  let titleOpacity = 1;
  let titleTransform = "none";
  let charsToShow = text.length;

  switch (animation) {
    case "fade":
      titleOpacity = Math.min(fadeIn, fadeOut);
      break;
    case "typewriter":
      charsToShow = Math.min(
        text.length,
        Math.floor((frame / durationInFrames) * text.length * 1.5),
      );
      titleOpacity = fadeOut;
      break;
    case "slide-up": {
      const translateY = interpolate(frame, [0, 20], [50, 0], {
        extrapolateRight: "clamp",
      });
      titleTransform = `translateY(${translateY}px)`;
      titleOpacity = Math.min(fadeIn, fadeOut);
      break;
    }
    case "scale": {
      const scale = spring({ fps, frame, config: { damping: 200 } });
      titleTransform = `scale(${0.5 + scale * 0.5})`;
      titleOpacity = Math.min(scale, fadeOut);
      break;
    }
  }

  return (
    <AbsoluteFill
      style={{
        backgroundColor,
        justifyContent: "center",
        alignItems: "center",
        opacity: titleOpacity,
      }}
    >
      <div
        style={{
          transform: titleTransform,
          textAlign: "center",
          padding: "0 60px",
        }}
      >
        <div
          style={{
            fontSize: 72,
            fontWeight: "bold",
            color,
            fontFamily: typography.fontFamily,
            lineHeight: 1.2,
          }}
        >
          {animation === "typewriter" ? text.slice(0, charsToShow) : text}
          {animation === "typewriter" && charsToShow < text.length && (
            <span style={{ opacity: frame % 20 < 10 ? 1 : 0 }}>|</span>
          )}
        </div>
        {subtitle && (
          <div
            style={{
              fontSize: 32,
              color: typography.accentColor,
              fontFamily: typography.fontFamily,
              marginTop: 16,
              opacity: interpolate(frame, [15, 40], [0, 1], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              }),
            }}
          >
            {subtitle}
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};
