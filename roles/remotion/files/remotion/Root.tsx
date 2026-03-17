import React from "react";
import { Composition } from "remotion";
import { HelloWorld } from "./HelloWorld/HelloWorld";
import { ReelMotionText } from "./ReelMotionText/ReelMotionText";
import { ReelMemeSkit } from "./ReelMemeSkit/ReelMemeSkit";
import { ReelFeatureShowcase } from "./ReelFeatureShowcase/ReelFeatureShowcase";
import { ReelTeaser } from "./ReelTeaser/ReelTeaser";

// Root compositions registry
// Add new compositions here as the Creative Studio grows

const defaultBrand = {
  name: "Default",
  palette: { primary: "#FF6B35", accent: "#2EC4B6" },
  typography: { heading: "sans-serif", body: "sans-serif" },
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
        id="ReelMotionText"
        component={ReelMotionText}
        durationInFrames={900}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{ scenes: [], brand: defaultBrand }}
      />
      <Composition
        id="ReelMemeSkit"
        component={ReelMemeSkit}
        durationInFrames={450}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{ scenes: [], brand: defaultBrand }}
      />
      <Composition
        id="ReelFeatureShowcase"
        component={ReelFeatureShowcase}
        durationInFrames={1800}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{ scenes: [], brand: defaultBrand }}
      />
      <Composition
        id="ReelTeaser"
        component={ReelTeaser}
        durationInFrames={450}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{ scenes: [], brand: defaultBrand }}
      />
    </>
  );
};
