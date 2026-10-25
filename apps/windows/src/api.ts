/* SpektraFilm Windows edition — GPLv3. See LICENSE in the repository root. */

export type Health = {
  status: string;
  sidecar: string;
  sidecar_version: string;
  protocol: number;
  python: string;
};

export type VersionInfo = {
  sidecar: string;
  protocol: number;
  spektrafilm: string | null;
  python: string;
};

export type Profile = {
  id: string;
  name: string;
  stage: string;
  type: string;
  support: string;
  use: string;
  channel_model: string;
  target_print: string | null;
};

export type ProfileList = {
  kind: "film" | "print";
  profiles: Profile[];
};

export type PreviewResult = {
  film_profile: string;
  print_profile: string;
  source: "builtin-chart" | "path" | string;
  image_path: string | null;
  width: number;
  height: number;
  mime: string;
  png_base64: string;
  elapsed_ms: number;
  preview_mode: boolean;
  max_size: number;
  exposure_compensation_ev: number;
  input_color_space: string;
  output_color_space: string;
};

export type PreviewRequest = {
  film_profile: string;
  print_profile: string;
  image_path: string | null;
  max_size: number;
  exposure_compensation_ev: number;
};

export function inTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

async function call<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<T>(command, args);
}

export function sidecarHealth(): Promise<Health> {
  return call<Health>("sidecar_health");
}

export function sidecarVersion(): Promise<VersionInfo> {
  return call<VersionInfo>("sidecar_version");
}

export function listFilmProfiles(): Promise<ProfileList> {
  return call<ProfileList>("list_film_profiles");
}

export function listPrintProfiles(): Promise<ProfileList> {
  return call<ProfileList>("list_print_profiles");
}

export function runPreview(params: PreviewRequest): Promise<PreviewResult> {
  return call<PreviewResult>("run_preview", { params });
}

export function formatErr(err: unknown): string {
  if (typeof err === "string") {
    return err;
  }
  if (err instanceof Error && err.message) {
    return err.message;
  }
  return "Unknown error";
}
