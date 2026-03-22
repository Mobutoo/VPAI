import React from "react";
import {
  AbsoluteFill,
  Sequence,
  type CalculateMetadataFunction,
} from "remotion";
import {
  TransitionSeries,
  linearTiming,
} from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { wipe } from "@remotion/transitions/wipe";
import { slide } from "@remotion/transitions/slide";

import type { MontageProps } from "./types";
import { Scene } from "./Scene";
import { TitleCard } from "./TitleCard";
import { Subtitles } from "./Subtitles";
import { AudioMix } from "./AudioMix";
import { buildColorGradeFilter, GrainOverlay } from "./effects";

function getPresentation(transitionType: string) {
  switch (transitionType) {
    case "crossfade":
      return fade();
    case "wipe":
      return wipe();
    case "slide":
      return slide();
    case "dip-to-black":
      // fade() over a black background (AbsoluteFill bg="#000") creates
      // a visual dip-to-black: scene A fades out → black visible → scene B fades in
      return fade();
    default:
      return fade();
  }
}

function computeTotalFrames(props: MontageProps): number {
  const titleFrames = props.title?.durationInFrames ?? 0;
  const outroFrames = props.outro?.durationInFrames ?? 0;

  let scenesFrames = 0;
  for (const scene of props.scenes) {
    scenesFrames += scene.durationInFrames;
  }

  // Subtract transition overlap between scenes (per-scene override aware)
  const transitionCount = Math.max(0, props.scenes.length - 1);
  const defaultDur = props.direction.defaultTransitionDurationFrames;
  let transitionOverlap = 0;
  for (let i = 0; i < transitionCount; i++) {
    const override = props.direction.sceneOverrides?.[i];
    const transType = override?.transition ?? props.direction.defaultTransition;
    if (transType !== "cut") {
      const dur = override?.transitionDurationFrames ?? defaultDur;
      transitionOverlap += dur;
    }
  }

  // Title/scene overlap to avoid black flash between title and first scene
  const titleOverlap = props.title ? Math.min(20, titleFrames) : 0;
  return titleFrames + scenesFrames - transitionOverlap - titleOverlap + outroFrames;
}

export const calculateMontageMetadata: CalculateMetadataFunction<
  MontageProps
> = async ({ props }) => {
  return {
    durationInFrames: Math.max(1, computeTotalFrames(props)),
    fps: props.fps,
    width: props.width,
    height: props.height,
  };
};

export const Montage: React.FC<MontageProps> = (props) => {
  const {
    scenes,
    title,
    outro,
    direction,
    subtitles,
    audio,
  } = props;

  const titleFrames = title?.durationInFrames ?? 0;
  // Overlap between title card and first scene to avoid black flash
  const titleOverlap = title ? Math.min(20, titleFrames) : 0;
  const totalFrames = computeTotalFrames(props);
  const colorFilter = buildColorGradeFilter(direction.colorGrade);

  // Compute scenes total (after transitions) for outro positioning
  let scenesNetFrames = 0;
  for (const scene of scenes) {
    scenesNetFrames += scene.durationInFrames;
  }
  const transitionCount = Math.max(0, scenes.length - 1);
  for (let i = 0; i < transitionCount; i++) {
    const override = direction.sceneOverrides?.[i];
    const transType = override?.transition ?? direction.defaultTransition;
    if (transType !== "cut") {
      const dur =
        override?.transitionDurationFrames ??
        direction.defaultTransitionDurationFrames;
      scenesNetFrames -= dur;
    }
  }

  const outroStart = titleFrames - titleOverlap + scenesNetFrames;

  return (
    <AbsoluteFill
      style={{ backgroundColor: "#000", filter: colorFilter !== "none" ? colorFilter : undefined }}
    >
      {/* Title card */}
      {title && (
        <Sequence durationInFrames={title.durationInFrames}>
          <TitleCard {...title} typography={direction.typography} />
        </Sequence>
      )}

      {/* Scenes with transitions — start slightly before title ends to crossfade */}
      <Sequence from={titleFrames - titleOverlap}>
        {direction.defaultTransition === "cut" ? (
          // No transitions — direct sequence
          <>
            {scenes.reduce<{ elements: React.ReactNode[]; offset: number }>(
              (acc, scene, i) => {
                acc.elements.push(
                  <Sequence
                    key={i}
                    from={acc.offset}
                    durationInFrames={scene.durationInFrames}
                  >
                    <Scene scene={scene} typography={direction.typography} />
                  </Sequence>,
                );
                return {
                  elements: acc.elements,
                  offset: acc.offset + scene.durationInFrames,
                };
              },
              { elements: [], offset: 0 },
            ).elements}
          </>
        ) : (
          // Transitions between scenes
          <TransitionSeries>
            {scenes.flatMap((scene, i) => {
              const override = direction.sceneOverrides?.[i];
              const transType =
                override?.transition ?? direction.defaultTransition;
              const transDur =
                override?.transitionDurationFrames ??
                direction.defaultTransitionDurationFrames;

              const elements: React.ReactNode[] = [
                <TransitionSeries.Sequence
                  key={`scene-${i}`}
                  durationInFrames={scene.durationInFrames}
                >
                  <Scene scene={scene} typography={direction.typography} />
                </TransitionSeries.Sequence>,
              ];

              if (i < scenes.length - 1 && transType !== "cut") {
                elements.push(
                  <TransitionSeries.Transition
                    key={`trans-${i}`}
                    presentation={getPresentation(transType)}
                    timing={linearTiming({
                      durationInFrames: transDur,
                    })}
                  />,
                );
              }

              return elements;
            })}
          </TransitionSeries>
        )}
      </Sequence>

      {/* Outro */}
      {outro && (
        <Sequence from={outroStart} durationInFrames={outro.durationInFrames}>
          <TitleCard {...outro} typography={direction.typography} />
        </Sequence>
      )}

      {/* Subtitles overlay */}
      {subtitles && subtitles.length > 0 && (
        <Subtitles
          lines={subtitles}
          style={direction.subtitleStyle}
          typography={direction.typography}
          offsetFrames={titleFrames}
        />
      )}

      {/* Audio */}
      {audio && (
        <AudioMix
          audio={audio}
          subtitles={subtitles}
          totalDurationInFrames={totalFrames}
          titleOffsetFrames={titleFrames}
        />
      )}

      {/* Grain overlay */}
      <GrainOverlay amount={direction.grain} />
    </AbsoluteFill>
  );
};
