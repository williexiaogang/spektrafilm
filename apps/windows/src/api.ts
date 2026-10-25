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

export type WhiteBalance = "as_shot" | "daylight" | "tungsten" | "custom";
export type RenderMode = "preview" | "scan";
export type PreviewSource = "builtin-chart" | "path" | "raw";

export type RawImport = {
  source: "raw";
  path: string;
  width: number;
  height: number;
  input_color_space: string;
  white_balance: WhiteBalance;
  temperature: number | null;
  tint: number | null;
  lens_correction: boolean;
  lens_summary: string | null;
  lens_applied: boolean;
  cached: boolean;
};

export type PreviewResult = {
  film_profile: string;
  print_profile: string;
  source: PreviewSource | string;
  image_path: string | null;
  input_width: number;
  input_height: number;
  width: number;
  height: number;
  mime: string;
  png_base64: string;
  reference_png_base64: string | null;
  elapsed_ms: number;
  render_mode: RenderMode;
  preview_mode: boolean;
  max_size: number;
  exposure_compensation_ev: number;
  y_filter_shift: number;
  m_filter_shift: number;
  halation_active: boolean;
  scatter_amount: number;
  scatter_spatial_scale: number;
  halation_amount: number;
  halation_spatial_scale: number;
  input_color_space: string;
  output_color_space: string;
  raw_cache: "hit" | "miss" | null;
  white_balance: WhiteBalance | null;
  lens_summary: string | null;
};

export type PreviewRequest = {
  film_profile: string;
  print_profile: string;
  source: PreviewSource;
  image_path: string | null;
  render_mode: RenderMode;
  max_size: number;
  exposure_compensation_ev: number;
  y_filter_shift: number;
  m_filter_shift: number;
  halation_active: boolean;
  scatter_amount: number;
  scatter_spatial_scale: number;
  halation_amount: number;
  halation_spatial_scale: number;
  white_balance?: WhiteBalance;
  temperature?: number;
  tint?: number;
  lens_correction?: boolean;
  input_color_space?: string;
  input_cctf_decoding?: boolean;
};

export type RawImportRequest = {
  path: string;
  white_balance: WhiteBalance;
  temperature: number;
  tint: number;
  lens_correction: boolean;
};

const RAW_EXTENSIONS = [
  "3fr",
  "arw",
  "cr2",
  "cr3",
  "crw",
  "dcr",
  "dng",
  "erf",
  "fff",
  "iiq",
  "kdc",
  "mef",
  "mos",
  "mrw",
  "nef",
  "nrw",
  "orf",
  "pef",
  "raf",
  "raw",
  "rw2",
  "rwl",
  "srw",
  "x3f",
];

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

export type StockThumb = {
  film_profile: string;
  print_profile: string;
  width: number;
  height: number;
  mime: string;
  png_base64: string;
  cached: boolean;
};

export function runPreview(params: PreviewRequest): Promise<PreviewResult> {
  return call<PreviewResult>("run_preview", { params });
}

// Keep at most one native thumbnail request in flight. Aborted strip refreshes
// are skipped before IPC so rapid stock changes cannot fill the Python queue.
let thumbnailQueue: Promise<unknown> = Promise.resolve();

export function stockThumb(params: {
  film_profile: string;
  print_profile: string;
  max_size?: number;
}, signal?: AbortSignal): Promise<StockThumb> {
  const request = thumbnailQueue.then(() => {
    if (signal?.aborted) {
      throw new DOMException("Thumbnail refresh cancelled", "AbortError");
    }
    return call<StockThumb>("stock_thumb", { params });
  });
  thumbnailQueue = request.catch(() => undefined);
  return request;
}

export function importRaw(params: RawImportRequest): Promise<RawImport> {
  return call<RawImport>("import_raw", { params });
}

export async function pickRawFile(): Promise<string | null> {
  const { open } = await import("@tauri-apps/plugin-dialog");
  const selected = await open({
    multiple: false,
    directory: false,
    title: "Open RAW",
    filters: [{ name: "Camera RAW", extensions: RAW_EXTENSIONS }],
  });
  if (Array.isArray(selected)) {
    return selected[0] ?? null;
  }
  return selected;
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
