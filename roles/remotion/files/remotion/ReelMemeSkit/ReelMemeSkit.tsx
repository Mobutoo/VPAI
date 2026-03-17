import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  Sequence,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { ReelProps } from "../types";

export const ReelMemeSkit: React.FC<ReelProps> = ({
  scenes,
  brand,
  audio,
}) => {
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

        return (
          <Sequence
            key={scene.scene_number}
            from={startFrame}
            durationInFrames={sceneDuration}
          >
            <MemeSceneContent scene={scene} brand={brand} />
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

interface MemeSceneContentProps {
  scene: ReelProps["scenes"][number];
  brand: ReelProps["brand"];
}

const MemeSceneContent: React.FC<MemeSceneContentProps> = ({
  scene,
  brand,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Ken Burns zoom-out effect
  const scaleAnim = spring({
    fps,
    frame,
    config: { damping: 200, stiffness: 80 },
    from: 1.1,
    to: 1.0,
  });

  const backgroundColor =
    brand.palette.background ?? "#1a1a2e";

  return (
    <AbsoluteFill
      style={{
        backgroundColor,
        transform: `scale(${scaleAnim})`,
      }}
    >
      {/* Background image if available */}
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

      {/* Top third: meme caption */}
      {scene.screen_text ? (
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            height: "33%",
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            padding: "20px 40px",
          }}
        >
          <div
            style={{
              fontSize: 56,
              fontWeight: "bold",
              color: "#ffffff",
              textTransform: "uppercase",
              fontFamily: brand.typography.heading,
              textAlign: "center",
              textShadow:
                "-2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 2px 2px 0 #000",
            }}
          >
            {scene.screen_text}
          </div>
        </div>
      ) : null}

      {/* Bottom third: dialogue bar */}
      {scene.dialogue ? (
        <div
          style={{
            position: "absolute",
            bottom: 0,
            left: 0,
            right: 0,
            backgroundColor: "rgba(0,0,0,0.7)",
            padding: 20,
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            minHeight: "15%",
          }}
        >
          <div
            style={{
              fontSize: 32,
              color: "#ffffff",
              fontFamily: brand.typography.body,
              textAlign: "center",
            }}
          >
            {scene.dialogue}
          </div>
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
