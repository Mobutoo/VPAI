import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  Sequence,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { ReelProps } from "../types";

export const ReelMotionText: React.FC<ReelProps> = ({
  scenes,
  brand,
  audio,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Calculate frame offsets for each scene
  const sceneFrames = scenes.map((scene) =>
    Math.ceil(scene.duration_sec * fps),
  );

  let cumulativeFrame = 0;

  return (
    <AbsoluteFill>
      {scenes.map((scene, index) => {
        const sceneDuration = sceneFrames[index];
        const startFrame = cumulativeFrame;
        cumulativeFrame += sceneDuration;

        const gradientAngle = scene.scene_number * 45;

        return (
          <Sequence
            key={scene.scene_number}
            from={startFrame}
            durationInFrames={sceneDuration}
          >
            <SceneContent
              scene={scene}
              sceneDuration={sceneDuration}
              gradientAngle={gradientAngle}
              brand={brand}
            />
          </Sequence>
        );
      })}

      {audio?.url ? (
        <Audio
          src={audio.url}
          startFrom={audio.startFrom ?? 0}
          volume={audio.volume ?? 1}
        />
      ) : null}
    </AbsoluteFill>
  );
};

interface SceneContentProps {
  scene: ReelProps["scenes"][number];
  sceneDuration: number;
  gradientAngle: number;
  brand: ReelProps["brand"];
}

const SceneContent: React.FC<SceneContentProps> = ({
  scene,
  sceneDuration,
  gradientAngle,
  brand,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const textOpacity = spring({
    fps,
    frame,
    config: { damping: 200 },
  });

  const textScale = spring({
    fps,
    frame,
    config: { damping: 100, stiffness: 150 },
    from: 0.8,
    to: 1,
  });

  // Crossfade out in the last 5 frames
  const fadeOut = interpolate(
    frame,
    [Math.max(0, sceneDuration - 5), sceneDuration],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  const displayText = scene.screen_text || scene.description;

  return (
    <AbsoluteFill style={{ opacity: fadeOut }}>
      {/* Background: gradient or image */}
      {scene.asset_url ? (
        <Img
          src={scene.asset_url}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            position: "absolute",
          }}
        />
      ) : null}

      <AbsoluteFill
        style={{
          background: scene.asset_url
            ? `linear-gradient(${gradientAngle}deg, ${brand.palette.primary}80, ${brand.palette.accent}80)`
            : `linear-gradient(${gradientAngle}deg, ${brand.palette.primary}, ${brand.palette.accent})`,
          justifyContent: "center",
          alignItems: "center",
          padding: 60,
        }}
      >
        <div
          style={{
            opacity: textOpacity,
            transform: `scale(${textScale})`,
            textAlign: "center",
          }}
        >
          <div
            style={{
              fontSize: 72,
              fontWeight: "bold",
              color: "#ffffff",
              fontFamily: brand.typography.heading,
              textShadow: "0 2px 20px rgba(0,0,0,0.5)",
              marginBottom: 24,
            }}
          >
            {displayText}
          </div>

          {scene.dialogue ? (
            <div
              style={{
                fontSize: 36,
                color: "#ffffff",
                fontFamily: brand.typography.body,
                textShadow: "0 2px 20px rgba(0,0,0,0.5)",
                opacity: 0.9,
              }}
            >
              {scene.dialogue}
            </div>
          ) : null}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
