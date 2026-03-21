import React from "react";
import { Composition } from "remotion";
import { HelloWorld } from "./HelloWorld/HelloWorld";
import { Montage, calculateMontageMetadata } from "./Montage";
import type { MontageProps } from "./Montage";

// Root compositions registry
// Add new compositions here as the Creative Studio grows

const defaultMontageProps: MontageProps = {
  scenes: [],
  fps: 30,
  width: 1920,
  height: 1080,
  direction: {
    pacing: "medium",
    defaultTransition: "crossfade",
    defaultTransitionDurationFrames: 15,
    colorGrade: {
      preset: "none",
      contrast: 1,
      saturation: 1,
      brightness: 1,
    },
    grain: 0,
    typography: {
      fontFamily: "Inter, sans-serif",
      accentColor: "#3b82f6",
      textColor: "#ffffff",
    },
    subtitleStyle: "cinema",
  },
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="HelloWorld"
        component={HelloWorld}
        durationInFrames={150}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{
          titleText: "VPAI Creative Studio",
          titleColor: "#ffffff",
        }}
      />
      <Composition
        id="Montage"
        component={Montage}
        durationInFrames={300}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={defaultMontageProps}
        calculateMetadata={calculateMontageMetadata}
      />
    </>
  );
};
