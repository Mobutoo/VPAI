import React from "react";
import { Composition } from "remotion";
import { HelloWorld } from "./HelloWorld/HelloWorld";

// Root compositions registry
// Add new compositions here as the Creative Studio grows

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
    </>
  );
};
