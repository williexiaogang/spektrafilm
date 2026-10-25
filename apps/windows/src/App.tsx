/* SpektraFilm Windows edition — GPLv3. See LICENSE in the repository root. */

import { useEffect, useMemo, useState } from "react";
import {
  formatErr,
  inTauri,
  listFilmProfiles,
  listPrintProfiles,
  runPreview,
  sidecarHealth,
  sidecarVersion,
  type Health,
  type PreviewResult,
  type Profile,
  type VersionInfo,
} from "./api";

const DRAFT_SIZE = 32;
const FINE_SIZE = 96;

type Phase = "booting" | "ready" | "error" | "offline";
type SourceMode = "chart" | "file";

export default function App() {
  const [phase, setPhase] = useState<Phase>("booting");
  const [bootError, setBootError] = useState<string | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [version, setVersion] = useState<VersionInfo | null>(null);
  const [films, setFilms] = useState<Profile[]>([]);
  const [papers, setPapers] = useState<Profile[]>([]);
  const [filmId, setFilmId] = useState("kodak_portra_400");
  const [paperId, setPaperId] = useState("kodak_portra_endura");
  const [exposure, setExposure] = useState(0);
  const [maxSize, setMaxSize] = useState(DRAFT_SIZE);
  const [sourceMode, setSourceMode] = useState<SourceMode>("chart");
  const [imagePath, setImagePath] = useState("");
  const [busy, setBusy] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [developedKey, setDevelopedKey] = useState<string | null>(null);

  useEffect(() => {
    if (!inTauri()) {
      setPhase("offline");
      setBootError(
        "This page is the Vite dev server on its own. Start the Tauri shell so it can launch the Python sidecar.",
      );
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const [healthInfo, versionInfo, filmList, paperList] = await Promise.all([
          sidecarHealth(),
          sidecarVersion(),
          listFilmProfiles(),
          listPrintProfiles(),
        ]);
        if (cancelled) {
          return;
        }
        setHealth(healthInfo);
        setVersion(versionInfo);
        setFilms(filmList.profiles);
        setPapers(paperList.profiles);
        setFilmId(
          filmList.profiles.find((profile) => profile.id === "kodak_portra_400")?.id ??
            filmList.profiles[0]?.id ??
            "",
        );
        setPaperId(
          paperList.profiles.find((profile) => profile.id === "kodak_portra_endura")?.id ??
            paperList.profiles[0]?.id ??
            "",
        );
        setPhase("ready");
      } catch (err) {
        if (!cancelled) {
          setBootError(formatErr(err));
          setPhase("error");
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const film = films.find((profile) => profile.id === filmId) ?? null;
  const paper = papers.find((profile) => profile.id === paperId) ?? null;
  const settingsKey = useMemo(
    () =>
      JSON.stringify({
        filmId,
        paperId,
        exposure,
        maxSize,
        sourceMode,
        imagePath: sourceMode === "file" ? imagePath.trim() : "",
      }),
    [exposure, filmId, imagePath, maxSize, paperId, sourceMode],
  );
  const stale = preview !== null && developedKey !== settingsKey;
  const shellReady = phase === "ready";

  async function develop() {
    if (!shellReady || busy || !filmId || !paperId) {
      return;
    }
    setBusy(true);
    setRunError(null);
    const requestKey = settingsKey;
    try {
      const result = await runPreview({
        film_profile: filmId,
        print_profile: paperId,
        image_path: sourceMode === "file" ? imagePath.trim() || null : null,
        max_size: maxSize,
        exposure_compensation_ev: exposure,
      });
      setPreview(result);
      setDevelopedKey(requestKey);
    } catch (err) {
      setRunError(formatErr(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="mark" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <div>
            <p className="wordmark">SpektraFilm</p>
            <p className="edition">Windows edition</p>
          </div>
        </div>
        <StatusPill phase={phase} />
      </header>

      <div className="workspace">
        <aside className="panel left-panel">
          <section>
            <h2>Film</h2>
            <label className="field">
              <span>Stock</span>
              <select
                value={films.some((profile) => profile.id === filmId) ? filmId : ""}
                disabled={!shellReady || films.length === 0}
                onChange={(event) => setFilmId(event.target.value)}
              >
                {films.length === 0 ? <option value="">No film profiles</option> : null}
                {films.map((profile) => (
                  <option key={profile.id} value={profile.id}>
                    {profile.name}
                  </option>
                ))}
              </select>
            </label>
            <MetaRow label="Type" value={film ? titleCase(film.type) : "—"} />
            <MetaRow label="Use" value={film ? titleCase(film.use) : "—"} />
            {film?.target_print ? (
              <p className="hint">Target print {labelFor(papers, film.target_print)}</p>
            ) : null}
          </section>

          <section>
            <h2>Print</h2>
            <label className="field">
              <span>Paper</span>
              <select
                value={papers.some((profile) => profile.id === paperId) ? paperId : ""}
                disabled={!shellReady || papers.length === 0}
                onChange={(event) => setPaperId(event.target.value)}
              >
                {papers.length === 0 ? <option value="">No print profiles</option> : null}
                {papers.map((profile) => (
                  <option key={profile.id} value={profile.id}>
                    {profile.name}
                  </option>
                ))}
              </select>
            </label>
            <MetaRow label="Support" value={paper ? titleCase(paper.support) : "—"} />
          </section>

          <section>
            <h2>Exposure</h2>
            <label className="field">
              <span className="split">
                <span>Compensation</span>
                <span className="value">{formatEv(exposure)}</span>
              </span>
              <input
                type="range"
                min={-2}
                max={2}
                step={0.1}
                value={exposure}
                disabled={!shellReady}
                onChange={(event) => setExposure(Number(event.target.value))}
              />
            </label>
            <div className="segmented" role="group" aria-label="Preview size">
              <button
                type="button"
                className={maxSize === DRAFT_SIZE ? "on" : ""}
                disabled={!shellReady}
                onClick={() => setMaxSize(DRAFT_SIZE)}
              >
                Draft
              </button>
              <button
                type="button"
                className={maxSize === FINE_SIZE ? "on" : ""}
                disabled={!shellReady}
                onClick={() => setMaxSize(FINE_SIZE)}
              >
                Fine
              </button>
            </div>
            <p className="hint">Draft keeps the preview small. The first run also warms Numba.</p>
          </section>

          <section>
            <h2>Source</h2>
            <div className="segmented" role="group" aria-label="Preview source">
              <button
                type="button"
                className={sourceMode === "chart" ? "on" : ""}
                disabled={!shellReady}
                onClick={() => setSourceMode("chart")}
              >
                Chart
              </button>
              <button
                type="button"
                className={sourceMode === "file" ? "on" : ""}
                disabled={!shellReady}
                onClick={() => setSourceMode("file")}
              >
                File
              </button>
            </div>
            {sourceMode === "file" ? (
              <label className="field">
                <span>Linear image path</span>
                <input
                  type="text"
                  value={imagePath}
                  disabled={!shellReady}
                  placeholder="C:\photos\scene_linear.tif"
                  onChange={(event) => setImagePath(event.target.value)}
                  spellCheck={false}
                />
              </label>
            ) : (
              <p className="hint">Built-in linear chart, treated as sRGB.</p>
            )}
          </section>

          <section className="later" aria-disabled="true">
            <h2>
              Print balance <em>Later</em>
            </h2>
            <FakeSlider label="Yellow filter" value={0} />
            <FakeSlider label="Magenta filter" value={0} />
            <h2>
              Texture <em>Later</em>
            </h2>
            <FakeSlider label="Grain" value={40} />
            <FakeSlider label="Halation" value={25} />
          </section>

          <div className="develop">
            <button
              type="button"
              className="primary"
              disabled={!shellReady || busy || !filmId || !paperId}
              onClick={() => {
                void develop();
              }}
            >
              {busy ? "Developing…" : "Develop preview"}
            </button>
            {runError ? <p className="error">{runError}</p> : null}
            {bootError && phase !== "ready" ? <p className="error">{bootError}</p> : null}
          </div>
        </aside>

        <main className="stage">
          <div className={`frame ${busy ? "busy" : ""}`}>
            {preview ? (
              <img
                alt="Simulation preview"
                src={`data:${preview.mime};base64,${preview.png_base64}`}
                style={{ imageRendering: preview.width < 200 ? "pixelated" : "auto" }}
              />
            ) : (
              <EmptyStage />
            )}
            {busy ? <div className="progress" /> : null}
          </div>
          <p className="caption">
            {preview
              ? preview.source === "path"
                ? preview.image_path
                : "Built-in color chart"
              : "No preview yet"}
            {stale ? <span className="stale">Settings changed</span> : null}
          </p>
        </main>

        <aside className="panel right-panel">
          <section>
            <h2>Preview</h2>
            <MetaRow label="Film" value={nameFor(films, preview?.film_profile)} />
            <MetaRow label="Paper" value={nameFor(papers, preview?.print_profile)} />
            <MetaRow
              label="Size"
              value={preview ? `${preview.width} × ${preview.height}` : "—"}
            />
            <MetaRow
              label="Time"
              value={preview ? `${(preview.elapsed_ms / 1000).toFixed(1)} s` : "—"}
            />
            <MetaRow
              label="Exposure"
              value={preview ? formatEv(preview.exposure_compensation_ev) : "—"}
            />
            <MetaRow label="Input" value={preview?.input_color_space ?? "—"} />
            <MetaRow label="Output" value={preview?.output_color_space ?? "sRGB"} />
            <MetaRow label="Mode" value={preview?.preview_mode ? "Preview" : "—"} />
          </section>

          <section>
            <h2>Sidecar</h2>
            <MetaRow label="Status" value={phaseLabel(phase)} />
            <MetaRow label="Python" value={health?.python ?? version?.python ?? "—"} />
            <MetaRow label="Runtime" value={version?.spektrafilm ?? "—"} />
            <MetaRow label="Protocol" value={health ? String(health.protocol) : "—"} />
          </section>

          <p className="legal">
            Simulation stays in <code>src/spektrafilm</code>. The Qt + napari GUI is still the
            research shell. This application is free software under the GNU GPL v3.
          </p>
        </aside>
      </div>
    </div>
  );
}

function StatusPill({ phase }: { phase: Phase }) {
  return (
    <p className={`pill ${phase}`}>
      <span />
      {phaseLabel(phase)}
    </p>
  );
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <p className="meta">
      <span>{label}</span>
      <strong>{value}</strong>
    </p>
  );
}

function FakeSlider({ label, value }: { label: string; value: number }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input type="range" min={0} max={100} value={value} disabled readOnly />
    </label>
  );
}

function EmptyStage() {
  return (
    <div className="empty">
      <div className="swatches" aria-hidden="true">
        <i />
        <i />
        <i />
        <i />
        <i />
        <i />
      </div>
      <p>Develop a preview</p>
      <span>Film and paper run through the spectral pipeline.</span>
    </div>
  );
}

function phaseLabel(phase: Phase): string {
  switch (phase) {
    case "booting":
      return "Starting sidecar";
    case "ready":
      return "Sidecar ready";
    case "offline":
      return "Shell offline";
    case "error":
      return "Sidecar error";
  }
}

function formatEv(value: number): string {
  const rounded = Math.round(value * 10) / 10;
  const text = rounded.toFixed(1);
  return rounded > 0 ? `+${text} EV` : `${text} EV`;
}

function titleCase(value: string): string {
  return value.replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function labelFor(profiles: Profile[], id: string): string {
  return profiles.find((profile) => profile.id === id)?.name ?? id;
}

function nameFor(profiles: Profile[], id: string | undefined): string {
  if (!id) {
    return "—";
  }
  return labelFor(profiles, id);
}
