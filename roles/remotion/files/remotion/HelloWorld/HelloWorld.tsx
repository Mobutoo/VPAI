import React from "react";
import {
  AbsoluteFill,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

interface HelloWorldProps {
  titleText: string;
  titleColor?: string;
}

export const HelloWorld: React.FC<HelloWorldProps> = ({
  titleText,
  titleColor = "#ffffff",
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const opacity = spring({
    fps,
    frame,
    config: { damping: 200 },
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#0f0f0f",
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      <div
        style={{
          fontSize: 80,
          fontWeight: "bold",
          color: titleColor,
          opacity,
          fontFamily: "sans-serif",
          textAlign: "center",
          padding: "0 40px",
        }}
      >
        {titleText}
      </div>
    </AbsoluteFill>
  );
};
