import React from "react";
import { AbsoluteFill } from "remotion";
import type { ArtisticDirection } from "./types";

const GRADE_PRESETS: Record<string, string> = {
  none: "none",
  warm: "sepia(0.15) saturate(1.2) brightness(1.05)",
  cold: "saturate(0.8) brightness(1.05) hue-rotate(10deg)",
  "teal-orange": "saturate(1.3) contrast(1.1) hue-rotate(-5deg)",
  vintage: "sepia(0.25) contrast(1.1) brightness(0.95)",
  "bleach-bypass": "saturate(0.4) contrast(1.4) brightness(0.9)",
};

export function buildColorGradeFilter(
  grade: ArtisticDirection["colorGrade"],
): string {
  const base = GRADE_PRESETS[grade.preset] ?? "none";
  if (base === "none" && grade.contrast === 1 && grade.saturation === 1 && grade.brightness === 1) {
    return "none";
  }
  const parts: string[] = [];
  if (base !== "none") {
    parts.push(base);
  }
  if (grade.contrast !== 1) {
    parts.push(`contrast(${grade.contrast})`);
  }
  if (grade.saturation !== 1) {
    parts.push(`saturate(${grade.saturation})`);
  }
  if (grade.brightness !== 1) {
    parts.push(`brightness(${grade.brightness})`);
  }
  return parts.join(" ") || "none";
}

export const GrainOverlay: React.FC<{ amount: number }> = ({ amount }) => {
  if (amount <= 0) return null;
  return (
    <AbsoluteFill
      style={{
        backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`,
        opacity: amount,
        mixBlendMode: "overlay",
        pointerEvents: "none",
      }}
    />
  );
};
