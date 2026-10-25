/* SpektraFilm Windows edition — GPLv3. See LICENSE in the repository root. */

import { useEffect, useMemo, useState } from "react";
import {
  formatErr,
  importRaw,
  inTauri,
  listFilmProfiles,
  listPrintProfiles,
  pickRawFile,
  runPreview,
  sidecarHealth,
  sidecarVersion,
  type Health,
  type PreviewResult,
  type Profile,
  type RawImport,
  type RenderMode,
  type VersionInfo,
  type WhiteBalance,
} from "./api";

const DRAFT_SIZE = 64;
const FINE_SIZE = 128;

type Phase = "booting" | "ready" | "error" | "offline";
type SourceMode = "chart" | "file" | "raw";
type Job = { tone: "idle" | "running" | "ok" | "error"; text: string };

const WHITE_BALANCE_OPTIONS: { id: WhiteBalance; label: string }[] = [
  { id: "as_shot", label: "As shot" },
  { id: "daylight", label: "Daylight" },
  { id: "tungsten", label: "Tungsten" },
  { id: "custom", label: "Custom" },
];

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
  const [yShift, setYShift] = useState(0);
  const [mShift, setMShift] = useState(0);
  const [halationActive, setHalationActive] = useState(true);
  const [scatterAmount, setScatterAmount] = useState(1);
  const [scatterSize, setScatterSize] = useState(1);
  const [halationAmount, setHalationAmount] = useState(1);
  const [halationSize, setHalationSize] = useState(1);
  const [renderMode, setRenderMode] = useState<RenderMode>("preview");
  const [maxSize, setMaxSize] = useState(DRAFT_SIZE);
  const [sourceMode, setSourceMode] = useState<SourceMode>("chart");
  const [imagePath, setImagePath] = useState("");
  const [rawPath, setRawPath] = useState("");
  const [whiteBalance, setWhiteBalance] = useState<WhiteBalance>("as_shot");
  const [temperature, setTemperature] = useState(5500);
  const [tint, setTint] = useState(1);
  const [lensCorrection, setLensCorrection] = useState(false);
  const [rawInfo, setRawInfo] = useState<RawImport | null>(null);
  const [busy, setBusy] = useState(false);
  const [job, setJob] = useState<Job>({ tone: "idle", text: "Idle" });
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
  const shellReady = phase === "ready";
  const customBalance = whiteBalance === "custom";
  const settingsKey = useMemo(
    () =>
      JSON.stringify({
        filmId,
        paperId,
        exposure,
        yShift,
        mShift,
        halationActive,
        scatterAmount,
        scatterSize,
        halationAmount,
        halationSize,
        renderMode,
        maxSize,
        sourceMode,
        imagePath: sourceMode === "file" ? imagePath.trim() : "",
        rawPath: sourceMode === "raw" ? rawPath.trim() : "",
        whiteBalance,
        temperature: customBalance ? temperature : null,
        tint: customBalance ? tint : null,
        lensCorrection,
      }),
    [
      customBalance,
      exposure,
      filmId,
      halationActive,
      halationAmount,
      halationSize,
      imagePath,
      lensCorrection,
      mShift,
      maxSize,
      paperId,
      rawPath,
      renderMode,
      scatterAmount,
      scatterSize,
      sourceMode,
      temperature,
      tint,
      whiteBalance,
      yShift,
    ],
  );
  const stale = preview !== null && developedKey !== settingsKey;

  function simulationParams() {
    return {
      film_profile: filmId,
      print_profile: paperId,
      render_mode: renderMode,
      max_size: maxSize,
      exposure_compensation_ev: exposure,
      y_filter_shift: yShift,
      m_filter_shift: mShift,
      halation_active: halationActive,
      scatter_amount: scatterAmount,
      scatter_spatial_scale: scatterSize,
      halation_amount: halationAmount,
      halation_spatial_scale: halationSize,
    };
  }

  function rawParams(path: string) {
    return {
      path,
      white_balance: whiteBalance,
      temperature,
      tint,
      lens_correction: lensCorrection,
    };
  }

  async function openRaw(path: string) {
    setBusy(true);
    setRunError(null);
    setJob({ tone: "running", text: "Opening RAW…" });
    try {
      const imported = await importRaw(rawParams(path));
      setRawInfo(imported);
      const lens =
        imported.lens_correction && !imported.lens_applied
          ? "Lens correction was not applied."
          : imported.lens_summary;
      setJob({
        tone: "ok",
        text: lens
          ? `RAW ready · ${imported.width}×${imported.height} · ${lens}`
          : `RAW ready · ${imported.width}×${imported.height}`,
      });
    } catch (err) {
      const message = formatErr(err);
      setRawInfo(null);
      setRunError(message);
      setJob({ tone: "error", text: message });
    } finally {
      setBusy(false);
    }
  }

  async function browseRaw() {
    if (!shellReady || busy) {
      return;
    }
    try {
      const picked = await pickRawFile();
      if (!picked) {
        return;
      }
      setRawPath(picked);
      setSourceMode("raw");
      await openRaw(picked);
    } catch (err) {
      const message = formatErr(err);
      setRunError(message);
      setJob({ tone: "error", text: message });
    }
  }

  async function develop() {
    if (!shellReady || busy || !filmId || !paperId) {
      return;
    }
    const filePath = imagePath.trim();
    const cameraPath = rawPath.trim();
    if (sourceMode === "file" && !filePath) {
      setRunError("Enter a linear image path, or switch back to the chart.");
      setJob({ tone: "error", text: "No linear image path." });
      return;
    }
    if (sourceMode === "raw" && !cameraPath) {
      setRunError("Choose a RAW file first.");
      setJob({ tone: "error", text: "No RAW file selected." });
      return;
    }

    setBusy(true);
    setRunError(null);
    const requestKey = settingsKey;
    const modeLabel = renderMode === "scan" ? "scan" : "preview";
    setJob({
      tone: "running",
      text: sourceMode === "raw" ? `Opening RAW and developing ${modeLabel}…` : `Developing ${modeLabel}…`,
    });
    try {
      const result = await runPreview({
        ...simulationParams(),
        source: sourceMode === "chart" ? "builtin-chart" : sourceMode === "file" ? "path" : "raw",
        image_path: sourceMode === "file" ? filePath : sourceMode === "raw" ? cameraPath : null,
        ...(sourceMode === "raw" ? rawParams(cameraPath) : {}),
      });
      setPreview(result);
      setDevelopedKey(requestKey);
      if (result.source === "raw") {
        setRawInfo((current) =>
          current && current.path === result.image_path
            ? current
            : {
                source: "raw",
                path: result.image_path ?? cameraPath,
                width: result.input_width,
                height: result.input_height,
                input_color_space: result.input_color_space,
                white_balance: result.white_balance ?? whiteBalance,
                temperature: customBalance ? temperature : null,
                tint: customBalance ? tint : null,
                lens_correction: lensCorrection,
                lens_summary: result.lens_summary,
                lens_applied: Boolean(result.lens_summary),
                cached: true,
              },
        );
      }
      const cache =
        result.raw_cache === "hit" ? " · RAW cache" : result.raw_cache === "miss" ? " · RAW decoded" : "";
      setJob({
        tone: "ok",
        text: `${modeLabel === "scan" ? "Scan" : "Preview"} ready · ${(result.elapsed_ms / 1000).toFixed(1)} s${cache}`,
      });
    } catch (err) {
      const message = formatErr(err);
      setRunError(message);
      setJob({ tone: "error", text: message });
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
        <StatusPill phase={phase} job={job} />
      </header>

      <div className="workspace">
        <aside className="panel left-panel">
          <section>
            <h2>Film</h2>
            <label className="field">
              <span title="Film stock passed to init_params">Stock</span>
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
            {film?.target_print ? (
              <p className="hint">Target print {labelFor(papers, film.target_print)}</p>
            ) : null}
          </section>

          <section>
            <h2>Print</h2>
            <label className="field">
              <span title="Print paper passed to init_params">Paper</span>
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
          </section>

          <section>
            <h2>Exposure</h2>
            <Slider
              label="Compensation"
              title="Bias added to the virtual camera auto-exposure, in stops"
              min={-3}
              max={3}
              step={0.1}
              value={exposure}
              disabled={!shellReady}
              display={formatEv(exposure)}
              onChange={setExposure}
            />
          </section>

          <section>
            <h2>Enlarger</h2>
            <Slider
              label="Yellow filter"
              title="enlarger.y_filter_shift, Kodak CC steps from neutral"
              min={-80}
              max={80}
              step={1}
              value={yShift}
              disabled={!shellReady}
              display={signed(yShift, 0)}
              onChange={setYShift}
            />
            <Slider
              label="Magenta filter"
              title="enlarger.m_filter_shift, Kodak CC steps from neutral"
              min={-80}
              max={80}
              step={1}
              value={mShift}
              disabled={!shellReady}
              display={signed(mShift, 0)}
              onChange={setMShift}
            />
          </section>

          <section>
            <h2>Halation</h2>
            <label className="check" title="film_render.halation.active">
              <input
                type="checkbox"
                checked={halationActive}
                disabled={!shellReady}
                onChange={(event) => setHalationActive(event.target.checked)}
              />
              Active
            </label>
            <Slider
              label="Scatter"
              title="film_render.halation.scatter_amount. 1 matches the stock model."
              min={0}
              max={2}
              step={0.05}
              value={scatterAmount}
              disabled={!shellReady || !halationActive}
              display={scatterAmount.toFixed(2)}
              onChange={setScatterAmount}
            />
            <Slider
              label="Scatter size"
              title="film_render.halation.scatter_spatial_scale"
              min={0}
              max={2}
              step={0.05}
              value={scatterSize}
              disabled={!shellReady || !halationActive}
              display={scatterSize.toFixed(2)}
              onChange={setScatterSize}
            />
            <Slider
              label="Halation"
              title="film_render.halation.halation_amount"
              min={0}
              max={2}
              step={0.05}
              value={halationAmount}
              disabled={!shellReady || !halationActive}
              display={halationAmount.toFixed(2)}
              onChange={setHalationAmount}
            />
            <Slider
              label="Halation size"
              title="film_render.halation.halation_spatial_scale"
              min={0}
              max={2}
              step={0.05}
              value={halationSize}
              disabled={!shellReady || !halationActive}
              display={halationSize.toFixed(2)}
              onChange={setHalationSize}
            />
          </section>

          <section>
            <h2>Develop</h2>
            <div className="segmented" role="group" aria-label="Render mode">
              <button
                type="button"
                className={renderMode === "preview" ? "on" : ""}
                disabled={!shellReady}
                title="settings.preview_mode on. Grain and several blurs are skipped."
                onClick={() => setRenderMode("preview")}
              >
                Preview
              </button>
              <button
                type="button"
                className={renderMode === "scan" ? "on" : ""}
                disabled={!shellReady}
                title="settings.preview_mode off, still limited to the size below."
                onClick={() => setRenderMode("scan")}
              >
                Scan
              </button>
            </div>
            <div className="segmented" role="group" aria-label="Preview size">
              <button
                type="button"
                className={maxSize === DRAFT_SIZE ? "on" : ""}
                disabled={!shellReady}
                onClick={() => setMaxSize(DRAFT_SIZE)}
              >
                Draft {DRAFT_SIZE}
              </button>
              <button
                type="button"
                className={maxSize === FINE_SIZE ? "on" : ""}
                disabled={!shellReady}
                onClick={() => setMaxSize(FINE_SIZE)}
              >
                Fine {FINE_SIZE}
              </button>
            </div>
            <p className="hint">Scan keeps grain and blur. Both modes resize to this long edge.</p>
          </section>

          <section>
            <h2>Source</h2>
            <div className="segmented three" role="group" aria-label="Preview source">
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
              <button
                type="button"
                className={sourceMode === "raw" ? "on" : ""}
                disabled={!shellReady}
                onClick={() => setSourceMode("raw")}
              >
                RAW
              </button>
            </div>
            {sourceMode === "file" ? (
              <label className="field">
                <span title="Scene-referred linear TIFF or EXR, read by load_image_oiio">Linear image path</span>
                <input
                  type="text"
                  value={imagePath}
                  disabled={!shellReady}
                  placeholder="C:\photos\scene_linear.tif"
                  onChange={(event) => setImagePath(event.target.value)}
                  spellCheck={false}
                />
              </label>
            ) : null}
            {sourceMode === "chart" ? <p className="hint">Built-in linear chart, treated as sRGB.</p> : null}
            {sourceMode === "raw" ? (
              <>
                <label className="field">
                  <span title="Same modes as the Qt importer: as shot, daylight, tungsten, custom">White balance</span>
                  <select
                    value={whiteBalance}
                    disabled={!shellReady}
                    onChange={(event) => setWhiteBalance(event.target.value as WhiteBalance)}
                  >
                    {WHITE_BALANCE_OPTIONS.map((option) => (
                      <option key={option.id} value={option.id}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <Slider
                  label="Temperature"
                  title="Kelvin. Used only for custom white balance."
                  min={2500}
                  max={9000}
                  step={50}
                  value={temperature}
                  disabled={!shellReady || !customBalance}
                  display={`${Math.round(temperature)} K`}
                  onChange={setTemperature}
                />
                <Slider
                  label="Tint"
                  title="Green-channel multiplier. 1 is neutral. Used only for custom white balance."
                  min={0.7}
                  max={1.3}
                  step={0.01}
                  value={tint}
                  disabled={!shellReady || !customBalance}
                  display={tint.toFixed(2)}
                  onChange={setTint}
                />
                <label className="check" title="lensfun correction during RAW import">
                  <input
                    type="checkbox"
                    checked={lensCorrection}
                    disabled={!shellReady}
                    onChange={(event) => setLensCorrection(event.target.checked)}
                  />
                  Lens correction
                </label>
                <label className="field">
                  <span>RAW path</span>
                  <input
                    type="text"
                    value={rawPath}
                    disabled={!shellReady}
                    placeholder="C:\photos\frame.nef"
                    spellCheck={false}
                    onChange={(event) => setRawPath(event.target.value)}
                  />
                </label>
                <div className="button-row">
                  <button type="button" className="secondary" disabled={!shellReady || busy} onClick={() => void browseRaw()}>
                    Browse
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    disabled={!shellReady || busy || !rawPath.trim()}
                    title="Demosaic again with the current white balance"
                    onClick={() => void openRaw(rawPath.trim())}
                  >
                    Reprocess
                  </button>
                </div>
              </>
            ) : null}
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
              {busy ? "Working…" : renderMode === "scan" ? "Develop scan" : "Develop preview"}
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
            <span>{captionFor(preview, sourceMode, rawPath, imagePath)}</span>
            {stale ? <span className="stale">Settings changed</span> : null}
          </p>
        </main>

        <aside className="panel right-panel">
          <section>
            <h2>Status</h2>
            <p className={`job ${job.tone}`}>{job.text}</p>
            <MetaRow label="Mode" value={preview ? titleCase(preview.render_mode) : titleCase(renderMode)} />
            <MetaRow
              label="Size"
              value={preview ? `${preview.width} × ${preview.height}` : "—"}
            />
            <MetaRow
              label="Time"
              value={preview ? `${(preview.elapsed_ms / 1000).toFixed(1)} s` : "—"}
            />
          </section>

          <section>
            <h2>RAW</h2>
            <MetaRow label="File" value={fileName(rawInfo?.path ?? (sourceMode === "raw" ? rawPath : ""))} />
            <MetaRow
              label="Frame"
              value={rawInfo ? `${rawInfo.width} × ${rawInfo.height}` : "—"}
            />
            <MetaRow label="Balance" value={rawInfo ? titleCase(rawInfo.white_balance) : titleCase(whiteBalance)} />
            <MetaRow label="Lens" value={rawInfo?.lens_summary ?? "—"} />
            <MetaRow label="Input" value={rawInfo?.input_color_space ?? "—"} />
          </section>

          <section>
            <h2>Preview</h2>
            <MetaRow label="Film" value={nameFor(films, preview?.film_profile)} />
            <MetaRow label="Paper" value={nameFor(papers, preview?.print_profile)} />
            <MetaRow
              label="Exposure"
              value={preview ? formatEv(preview.exposure_compensation_ev) : formatEv(exposure)}
            />
            <MetaRow
              label="Y / M"
              value={
                preview
                  ? `${signed(preview.y_filter_shift, 0)} / ${signed(preview.m_filter_shift, 0)}`
                  : `${signed(yShift, 0)} / ${signed(mShift, 0)}`
              }
            />
            <MetaRow label="Output" value={preview?.output_color_space ?? "sRGB"} />
          </section>

          <section>
            <h2>Sidecar</h2>
            <MetaRow label="Status" value={phaseLabel(phase)} />
            <MetaRow label="Python" value={health?.python ?? version?.python ?? "—"} />
            <MetaRow label="Runtime" value={version?.spektrafilm ?? "—"} />
            <MetaRow label="Protocol" value={health ? String(health.protocol) : "—"} />
          </section>

          <p className="legal">
            Simulation stays in <code>src/spektrafilm</code>. RAW import uses the same rawpy helper
            as the Qt GUI. This application is free software under the GNU GPL v3.
          </p>
        </aside>
      </div>
    </div>
  );
}

function StatusPill({ phase, job }: { phase: Phase; job: Job }) {
  const tone = job.tone === "running" ? "booting" : job.tone === "error" ? "error" : phase;
  const label = job.tone === "running" || job.tone === "error" ? job.text : phaseLabel(phase);
  return (
    <p className={`pill ${tone}`} title={job.text}>
      <span />
      {label.length > 42 ? `${label.slice(0, 40)}…` : label}
    </p>
  );
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <p className="meta">
      <span>{label}</span>
      <strong title={value}>{value}</strong>
    </p>
  );
}

function Slider({
  label,
  title,
  min,
  max,
  step,
  value,
  display,
  disabled,
  onChange,
}: {
  label: string;
  title: string;
  min: number;
  max: number;
  step: number;
  value: number;
  display: string;
  disabled: boolean;
  onChange: (value: number) => void;
}) {
  return (
    <label className={`field ${disabled ? "is-off" : ""}`}>
      <span className="split" title={title}>
        <span>{label}</span>
        <span className="value">{display}</span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        aria-label={label}
        onChange={(event) => onChange(Number(event.target.value))}
      />
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
      <span>Open a RAW file or use the built-in chart.</span>
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

function signed(value: number, digits: number): string {
  const text = value.toFixed(digits);
  return value > 0 ? `+${text}` : text;
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

function fileName(path: string): string {
  const trimmed = path.trim();
  if (!trimmed) {
    return "—";
  }
  const parts = trimmed.split(/[/\\]/);
  return parts[parts.length - 1] || trimmed;
}

function captionFor(
  preview: PreviewResult | null,
  sourceMode: SourceMode,
  rawPath: string,
  imagePath: string,
): string {
  if (preview?.source === "raw") {
    return fileName(preview.image_path ?? rawPath);
  }
  if (preview?.source === "path") {
    return preview.image_path ?? "Linear file";
  }
  if (preview) {
    return "Built-in color chart";
  }
  if (sourceMode === "raw" && rawPath.trim()) {
    return fileName(rawPath);
  }
  if (sourceMode === "file" && imagePath.trim()) {
    return fileName(imagePath);
  }
  return "No preview yet";
}
