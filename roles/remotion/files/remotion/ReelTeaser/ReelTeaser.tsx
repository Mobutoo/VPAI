import React from "react";
import {
  AbsoluteFill,
  Audio,
  Sequence,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { ReelProps } from "../types";

export const ReelTeaser: React.FC<ReelProps> = ({
  scenes,
  brand,
  audio,
}) => {
  const { fps } = useVideoConfig();

  const sceneFrames = scenes.map((scene) =>
    Math.ceil(scene.duration_sec * fps),
  );

  let cumulativeFrame = 0;

  return (
    <AbsoluteFill style={{ backgroundColor: "#0a0a0a" }}>
      {scenes.map((scene, index) => {
        const sceneDuration = sceneFrames[index];
        const startFrame = cumulativeFrame;
        cumulativeFrame += sceneDuration;

        const isFirst = index === 0;
        const isLast = index === scenes.length - 1;

        return (
          <Sequence
            key={scene.scene_number}
            from={startFrame}
            durationInFrames={sceneDuration}
          >
            {/* Accent flash at scene start (2 frames) */}
            {index > 0 ? (
              <AccentFlash color={brand.palette.accent} />
            ) : null}

            {isFirst ? (
              <BlurRevealScene scene={scene} brand={brand} />
            ) : isLast ? (
              <CTAScene scene={scene} brand={brand} />
            ) : (
              <RapidCutScene scene={scene} brand={brand} />
            )}
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

interface AccentFlashProps {
  color: string;
}

const AccentFlash: React.FC<AccentFlashProps> = ({ color }) => {
  const frame = useCurrentFrame();

  // 2-frame flash at the start of each scene transition
  const opacity = frame < 2 ? 1 : 0;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: color,
        opacity,
        zIndex: 10,
      }}
    />
  );
};

interface SceneComponentProps {
  scene: ReelProps["scenes"][number];
  brand: ReelProps["brand"];
}

const BlurRevealScene: React.FC<SceneComponentProps> = ({
  scene,
  brand,
}) => {
  const frame = useCurrentFrame();

  // Reveal from blur(8px) to blur(0px) over 15 frames
  const blurAmount = interpolate(
    frame,
    [0, 15],
    [8, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  const displayText = scene.screen_text ?? scene.description;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#0a0a0a",
        justifyContent: "center",
        alignItems: "center",
        padding: 60,
      }}
    >
      <div
        style={{
          fontSize: 72,
          fontWeight: "bold",
          color: "#ffffff",
          fontFamily: brand.typography.heading,
          textTransform: "uppercase",
          letterSpacing: 4,
          textAlign: "center",
          filter: `blur(${blurAmount}px)`,
        }}
      >
        {displayText}
      </div>
    </AbsoluteFill>
  );
};

const RapidCutScene: React.FC<SceneComponentProps> = ({
  scene,
  brand,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Text slides up from bottom
  const translateY = spring({
    fps,
    frame,
    config: { damping: 100, stiffness: 300 },
    from: 50,
    to: 0,
  });

  const displayText = scene.screen_text ?? scene.description;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#0a0a0a",
        justifyContent: "center",
        alignItems: "center",
        padding: 60,
      }}
    >
      <div
        style={{
          fontSize: 64,
          fontWeight: "bold",
          color: "#ffffff",
          fontFamily: brand.typography.heading,
          textTransform: "uppercase",
          letterSpacing: 4,
          textAlign: "center",
          transform: `translateY(${translateY}px)`,
        }}
      >
        {displayText}
      </div>
    </AbsoluteFill>
  );
};

const CTAScene: React.FC<SceneComponentProps> = ({
  scene,
  brand,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const scale = spring({
    fps,
    frame,
    config: { damping: 80, stiffness: 200 },
    from: 0.5,
    to: 1,
  });

  const displayText = scene.screen_text ?? scene.description;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: brand.palette.primary,
        justifyContent: "center",
        alignItems: "center",
        padding: 60,
      }}
    >
      <div
        style={{
          fontSize: 80,
          fontWeight: "bold",
          color: "#ffffff",
          fontFamily: brand.typography.heading,
          textTransform: "uppercase",
          letterSpacing: 4,
          textAlign: "center",
          transform: `scale(${scale})`,
        }}
      >
        {displayText}
      </div>
    </AbsoluteFill>
  );
};
