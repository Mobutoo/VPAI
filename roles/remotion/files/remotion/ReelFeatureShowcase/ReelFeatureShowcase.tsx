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

export const ReelFeatureShowcase: React.FC<ReelProps> = ({
  scenes,
  brand,
  audio,
}) => {
  const { fps } = useVideoConfig();

  const sceneFrames = scenes.map((scene) =>
    Math.ceil(scene.duration_sec * fps),
  );

  // Add 1-second intro if scenes exist
  const introFrames = scenes.length > 0 ? fps : 0;
  let cumulativeFrame = introFrames;

  return (
    <AbsoluteFill>
      {/* Brand intro — 1 second */}
      {introFrames > 0 ? (
        <Sequence from={0} durationInFrames={introFrames}>
          <BrandIntro brand={brand} />
        </Sequence>
      ) : null}

      {scenes.map((scene, index) => {
        const sceneDuration = sceneFrames[index];
        const startFrame = cumulativeFrame;
        cumulativeFrame += sceneDuration;
        const isLast = index === scenes.length - 1;

        return (
          <Sequence
            key={scene.scene_number}
            from={startFrame}
            durationInFrames={sceneDuration}
          >
            <ShowcaseSceneContent
              scene={scene}
              brand={brand}
              isLast={isLast}
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

interface BrandIntroProps {
  brand: ReelProps["brand"];
}

const BrandIntro: React.FC<BrandIntroProps> = ({ brand }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const scale = spring({
    fps,
    frame,
    config: { damping: 100, stiffness: 200 },
    from: 0.5,
    to: 1,
  });

  return (
    <AbsoluteFill
      style={{
        background: `linear-gradient(135deg, ${brand.palette.primary}, ${brand.palette.accent})`,
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      <div
        style={{
          fontSize: 96,
          fontWeight: "bold",
          color: "#ffffff",
          fontFamily: brand.typography.heading,
          transform: `scale(${scale})`,
          textShadow: "0 4px 30px rgba(0,0,0,0.3)",
        }}
      >
        {brand.name}
      </div>
    </AbsoluteFill>
  );
};

interface ShowcaseSceneContentProps {
  scene: ReelProps["scenes"][number];
  brand: ReelProps["brand"];
  isLast: boolean;
}

const ShowcaseSceneContent: React.FC<ShowcaseSceneContentProps> = ({
  scene,
  brand,
  isLast,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Overlay slides up from bottom
  const overlayTranslateY = interpolate(
    frame,
    [0, 10],
    [100, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  // CTA pulse for last scene
  const ctaScale = isLast
    ? Math.sin(frame * 0.1) * 0.1 + 1
    : 1;

  return (
    <AbsoluteFill>
      {/* Main area — top 75% */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: "75%",
          overflow: "hidden",
        }}
      >
        {scene.asset_url ? (
          <Img
            src={scene.asset_url}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
            }}
          />
        ) : (
          <AbsoluteFill
            style={{
              background: `linear-gradient(180deg, ${brand.palette.primary}CC, ${brand.palette.accent}CC)`,
              justifyContent: "center",
              alignItems: "center",
              padding: 40,
            }}
          >
            <div
              style={{
                fontSize: 48,
                color: "#ffffff",
                fontFamily: brand.typography.body,
                textAlign: "center",
                textShadow: "0 2px 10px rgba(0,0,0,0.3)",
              }}
            >
              {scene.description}
            </div>
          </AbsoluteFill>
        )}

        {/* Brand badge — top right */}
        <div
          style={{
            position: "absolute",
            top: 20,
            right: 20,
            backgroundColor: brand.palette.accent,
            borderRadius: 8,
            padding: "6px 16px",
          }}
        >
          <div
            style={{
              fontSize: 18,
              fontWeight: "bold",
              color: "#ffffff",
              fontFamily: brand.typography.body,
            }}
          >
            {brand.name}
          </div>
        </div>
      </div>

      {/* Bottom overlay strip — bottom 25% */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          right: 0,
          height: "25%",
          backgroundColor: `${brand.palette.primary}D9`,
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          padding: "0 40px",
          transform: `translateY(${overlayTranslateY}%)`,
        }}
      >
        <div
          style={{
            fontSize: 40,
            fontWeight: "bold",
            color: "#ffffff",
            fontFamily: brand.typography.heading,
            textAlign: "center",
            transform: isLast ? `scale(${ctaScale})` : undefined,
          }}
        >
          {scene.screen_text ?? (isLast ? "Swipe up" : scene.description)}
        </div>
      </div>
    </AbsoluteFill>
  );
};
