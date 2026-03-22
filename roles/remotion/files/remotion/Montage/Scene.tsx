import React from "react";
import {
  AbsoluteFill,
  Img,
  OffthreadVideo,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { SceneData, ArtisticDirection } from "./types";

interface SceneProps {
  scene: SceneData;
  typography: ArtisticDirection["typography"];
}

const KenBurnsImage: React.FC<{
  src: string;
  kenBurns: NonNullable<SceneData["kenBurns"]>;
}> = ({ src, kenBurns }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  const scale = interpolate(
    frame,
    [0, durationInFrames],
    [kenBurns.startScale, kenBurns.endScale],
  );
  const translateX = interpolate(
    frame,
    [0, durationInFrames],
    [0, kenBurns.panX * 50],
  );
  const translateY = interpolate(
    frame,
    [0, durationInFrames],
    [0, kenBurns.panY * 50],
  );

  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      <Img
        src={src}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transform: `scale(${scale}) translate(${translateX}px, ${translateY}px)`,
        }}
      />
    </AbsoluteFill>
  );
};

const OverlayText: React.FC<{
  overlay: NonNullable<SceneData["overlay"]>;
  typography: ArtisticDirection["typography"];
}> = ({ overlay, typography }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 15], [0, 1], {
    extrapolateRight: "clamp",
  });

  const positionStyle: React.CSSProperties = {
    position: "absolute",
    padding: "8px 16px",
    color: typography.textColor,
    fontFamily: typography.fontFamily,
    fontSize: 24,
    fontWeight: "bold",
    textShadow: "2px 2px 4px rgba(0,0,0,0.7)",
    opacity,
  };

  switch (overlay.position) {
    case "bottom-left":
      return (
        <div style={{ ...positionStyle, bottom: 40, left: 40 }}>
          {overlay.text}
        </div>
      );
    case "bottom-center":
      return (
        <div
          style={{
            ...positionStyle,
            bottom: 40,
            left: 0,
            right: 0,
            textAlign: "center",
          }}
        >
          {overlay.text}
        </div>
      );
    case "top-left":
      return (
        <div style={{ ...positionStyle, top: 40, left: 40 }}>
          {overlay.text}
        </div>
      );
  }
};

export const Scene: React.FC<SceneProps> = ({ scene, typography }) => {
  return (
    <AbsoluteFill>
      {scene.type === "video" && (
        <OffthreadVideo
          src={scene.src}
          toneMapped={false}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      )}

      {scene.type === "keyframe" && scene.kenBurns && (
        <KenBurnsImage src={scene.src} kenBurns={scene.kenBurns} />
      )}
      {scene.type === "keyframe" && !scene.kenBurns && (
        <Img
          src={scene.src}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      )}

      {scene.type === "metube-remix" && (
        <OffthreadVideo
          src={scene.src}
          trimBefore={scene.startFromFrame ?? 0}
          toneMapped={false}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      )}

      {scene.overlay && (
        <OverlayText overlay={scene.overlay} typography={typography} />
      )}
    </AbsoluteFill>
  );
};
