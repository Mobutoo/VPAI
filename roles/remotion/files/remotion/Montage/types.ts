/** Type de contenu d'une scene */
export type SceneType = "video" | "keyframe" | "metube-remix";

/** Une scene dans la timeline */
export interface SceneData {
  type: SceneType;
  src: string;
  durationInFrames: number;
  sceneIndex: number;

  kenBurns?: {
    startScale: number;
    endScale: number;
    panX: number;
    panY: number;
  };

  startFromFrame?: number;

  overlay?: {
    text: string;
    position: "bottom-left" | "bottom-center" | "top-left";
  };
}

/** Carte titre (intro ou outro) */
export interface TitleData {
  text: string;
  subtitle?: string;
  color: string;
  backgroundColor: string;
  durationInFrames: number;
  animation: "fade" | "typewriter" | "slide-up" | "scale";
}

/** Ligne de sous-titre (pre-parsee depuis SRT par Python) */
export interface SubtitleLine {
  text: string;
  startMs: number;
  endMs: number;
}

/** Configuration audio */
export interface AudioData {
  musicSrc?: string;
  voiceoverSrc?: string;
  musicVolume: number;
  voiceoverVolume: number;
  duckMusicOnVo: boolean;
  duckLevel: number;
  musicFadeInFrames: number;
  musicFadeOutFrames: number;
}

/** Direction artistique */
export interface ArtisticDirection {
  pacing: "slow" | "medium" | "fast" | "dynamic";

  defaultTransition: "cut" | "crossfade" | "dip-to-black" | "wipe" | "slide";
  defaultTransitionDurationFrames: number;
  sceneOverrides?: Record<
    number,
    {
      transition?: string;
      transitionDurationFrames?: number;
      durationOverrideFrames?: number;
    }
  >;

  colorGrade: {
    preset:
      | "none"
      | "warm"
      | "cold"
      | "teal-orange"
      | "vintage"
      | "bleach-bypass";
    contrast: number;
    saturation: number;
    brightness: number;
  };
  grain: number;

  typography: {
    fontFamily: string;
    accentColor: string;
    textColor: string;
  };

  subtitleStyle: "reel" | "cinema" | "minimal" | "bold-center" | "karaoke";
}

/** Props completes de la composition Montage */
export interface MontageProps {
  scenes: SceneData[];
  title?: TitleData;
  outro?: TitleData;
  direction: ArtisticDirection;
  subtitles?: SubtitleLine[];
  audio?: AudioData;
  fps: number;
  width: number;
  height: number;
}
