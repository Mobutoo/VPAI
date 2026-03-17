export interface SceneData {
  scene_number: number;
  description: string;
  dialogue?: string;
  screen_text?: string;
  duration_sec: number;
  transition: "cut" | "fade" | "zoom" | "swipe" | "blur";
  visual_type: "motion_design" | "ai_generative" | "stock" | "meme";
  asset_url?: string;
}

export interface BrandProfile {
  name: string;
  palette: { primary: string; accent: string; background?: string };
  typography: { heading: string; body: string };
  logo_url?: string;
}

export interface AudioConfig {
  url?: string;
  startFrom?: number;
  volume?: number;
}

export interface ReelProps {
  scenes: SceneData[];
  brand: BrandProfile;
  audio?: AudioConfig;
}
