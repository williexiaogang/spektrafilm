/* SpektraFilm Windows edition — GPLv3. See LICENSE in the repository root. */

import {
  useEffect,
  useMemo,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
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
  stockThumb,
  type Health,
  type PreviewResult,
  type Profile,
  type RawImport,
  type RenderMode,
  type VersionInfo,
  type WhiteBalance,
} from "./api";
import { filmSwatch, GHOST_FILMS, GHOST_PAPERS, paperSwatch } from "./swatches";

const DRAFT_SIZE = 64;
const FINE_SIZE = 128;
const THUMB_SIZE = 96;
const THUMB_DEBOUNCE_MS = 180;
const INSPECTOR_DEFAULT = 268;
const INSPECTOR_MIN = 210;
const INSPECTOR_MAX = 440;

type Phase = "booting" | "ready" | "error" | "offline";
type SourceMode = "chart" | "file" | "raw";
type Job = { tone: "idle" | "running" | "ok" | "error"; text: string };
type Named = { id: string; name: string };
type KeptFrame = { id: number; result: PreviewResult; key: string };

const WHITE_BALANCE_OPTIONS: { id: WhiteBalance; label: string; title: string }[] = [
  { id: "as_shot", label: "Shot", title: "As shot — camera white balance" },
  { id: "daylight", label: "Day", title: "Daylight" },
  { id: "tungsten", label: "Tung", title: "Tungsten" },
  { id: "custom", label: "Custom", title: "Custom Kelvin and green-channel tint" },
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
  const [frames, setFrames] = useState<KeptFrame[]>([]);
  const [shownId, setShownId] = useState<number | null>(null);
  const [comparing, setComparing] = useState(false);
  const [inspectorWidth, setInspectorWidth] = useState(INSPECTOR_DEFAULT);
  const [filmThumbs, setFilmThumbs] = useState<Record<string, string>>({});
  const [paperThumbs, setPaperThumbs] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!inTauri()) {
      setPhase("offline");
      setBootError("Start the Tauri shell so it can launch the Python sidecar.");
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

  const shellReady = phase === "ready";
  const filmKey = films.map((profile) => profile.id).join("|");
  const paperKey = papers.map((profile) => profile.id).join("|");

  useEffect(() => {
    if (!shellReady || !paperId || films.length === 0) {
      return;
    }
    let cancelled = false;
    const selected = filmId;
    const order = [...films].sort((a, b) => Number(b.id === selected) - Number(a.id === selected));
    setFilmThumbs({});
    const timer = window.setTimeout(() => {
      void (async () => {
        for (const profile of order) {
          if (cancelled) {
            return;
          }
          try {
            const thumb = await stockThumb({
              film_profile: profile.id,
              print_profile: paperId,
              max_size: THUMB_SIZE,
            });
            if (cancelled) {
              return;
            }
            setFilmThumbs((current) => ({
              ...current,
              [profile.id]: `data:${thumb.mime};base64,${thumb.png_base64}`,
            }));
          } catch {
            // The color study stays in the frame when a thumb cannot be encoded.
          }
        }
      })();
    }, THUMB_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
    // The selected stock is ordered first, but changing it must not rebake the strip.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shellReady, paperId, filmKey]);

  useEffect(() => {
    if (!shellReady || !filmId || papers.length === 0) {
      return;
    }
    let cancelled = false;
    const selected = paperId;
    const order = [...papers].sort((a, b) => Number(b.id === selected) - Number(a.id === selected));
    setPaperThumbs({});
    const timer = window.setTimeout(() => {
      void (async () => {
        for (const profile of order) {
          if (cancelled) {
            return;
          }
          try {
            const thumb = await stockThumb({
              film_profile: filmId,
              print_profile: profile.id,
              max_size: THUMB_SIZE,
            });
            if (cancelled) {
              return;
            }
            setPaperThumbs((current) => ({
              ...current,
              [profile.id]: `data:${thumb.mime};base64,${thumb.png_base64}`,
            }));
          } catch {
            // The paper color study stays until a thumb arrives.
          }
        }
      })();
    }, THUMB_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shellReady, filmId, paperKey]);
  const customBalance = whiteBalance === "custom";
  const filmTiles: Named[] = films.length > 0 ? films : GHOST_FILMS;
  const paperTiles: Named[] = papers.length > 0 ? papers : GHOST_PAPERS;
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
  const canCompare = Boolean(preview?.reference_png_base64);
  const viewPng =
    comparing && preview?.reference_png_base64 ? preview.reference_png_base64 : preview?.png_base64;

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

  function holdCompare(next: boolean) {
    if (next && !canCompare) {
      return;
    }
    setComparing(next);
  }

  function resizeInspector(event: ReactPointerEvent<HTMLDivElement>) {
    event.preventDefault();
    const startX = event.clientX;
    const startW = inspectorWidth;
    const move = (ev: PointerEvent) => {
      const next = startW - (ev.clientX - startX);
      setInspectorWidth(Math.min(INSPECTOR_MAX, Math.max(INSPECTOR_MIN, next)));
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
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
      setRunError("Enter a linear image path.");
      setJob({ tone: "error", text: "No linear image path." });
      return;
    }
    if (sourceMode === "raw" && !cameraPath) {
      setRunError("Choose a RAW file first.");
      setJob({ tone: "error", text: "No RAW file selected." });
      return;
    }

    setBusy(true);
    setComparing(false);
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
      const id = Date.now();
      setPreview(result);
      setDevelopedKey(requestKey);
      setShownId(id);
      setFrames((current) => [{ id, result, key: requestKey }, ...current].slice(0, 8));
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

  const lampTitle = [
    job.text,
    health?.python ? `Python ${health.python}${health.bundled ? " · bundled" : ""}` : "",
    version?.spektrafilm ? `spektrafilm ${version.spektrafilm}` : "",
    health ? `protocol ${health.protocol}` : "",
  ]
    .filter(Boolean)
    .join("\n");

  return (
    <div className="app">
      <header className="mast">
        <div className="brand">
          <DyeMark />
          <div>
            <p className="wordmark" title="SpektraFilm Windows edition. GNU GPL v3.">
              SpektraFilm
            </p>
            <p className="edition">Windows</p>
          </div>
        </div>
        <div className="mast-tools">
          <div className="chips" role="group" aria-label="Source">
            <button
              type="button"
              className={sourceMode === "chart" ? "on" : ""}
              disabled={!shellReady}
              title="Built-in linear chart, treated as sRGB"
              onClick={() => setSourceMode("chart")}
            >
              Chart
            </button>
            <button
              type="button"
              className={sourceMode === "file" ? "on" : ""}
              disabled={!shellReady}
              title="Scene-referred linear TIFF or EXR"
              onClick={() => setSourceMode("file")}
            >
              File
            </button>
            <button
              type="button"
              className={sourceMode === "raw" ? "on" : ""}
              disabled={!shellReady}
              title="Camera RAW, demosaiced by the sidecar"
              onClick={() => setSourceMode("raw")}
            >
              RAW
            </button>
          </div>
          <button
            type="button"
            className="expose"
            disabled={!shellReady || busy || !filmId || !paperId}
            title="Develop the current stock, paper, and filters"
            onClick={() => {
              void develop();
            }}
          >
            {busy ? "Working" : renderMode === "scan" ? "Scan" : "Expose"}
          </button>
          <StatusPill phase={phase} job={job} title={lampTitle} />
        </div>
      </header>

      <StockStrip
        label="Film"
        kind="film"
        profiles={filmTiles}
        selected={filmId}
        disabled={!shellReady}
        thumbs={filmThumbs}
        pending={shellReady}
        onSelect={setFilmId}
      />
      <StockStrip
        label="Paper"
        kind="paper"
        profiles={paperTiles}
        selected={paperId}
        disabled={!shellReady}
        thumbs={paperThumbs}
        pending={shellReady}
        onSelect={setPaperId}
      />

      <div
        className="workspace"
        style={{ ["--inspector" as string]: `${inspectorWidth}px` }}
      >
        <main className="stage">
          <div
            className={`frame ${busy ? "busy" : ""} ${preview ? "holding" : ""} ${comparing ? "comparing" : ""} ${stale ? "is-stale" : ""}`}
            onPointerDown={() => holdCompare(true)}
            onPointerUp={() => holdCompare(false)}
            onPointerLeave={() => holdCompare(false)}
            onPointerCancel={() => holdCompare(false)}
          >
            <div className="marks" aria-hidden="true">
              <i />
              <i />
              <i />
              <i />
            </div>
            {preview && viewPng ? (
              <img
                key={comparing ? "reference" : String(shownId ?? "print")}
                alt={comparing ? "Scene before development" : "Developed preview"}
                src={`data:${preview.mime};base64,${viewPng}`}
                style={{ imageRendering: preview.width < 200 ? "pixelated" : "auto" }}
              />
            ) : (
              <EmptyStage />
            )}
            {busy ? <div className="sweep" /> : null}
            {comparing ? <span className="compare-tag">Original</span> : null}
            {canCompare ? (
              <button
                type="button"
                className={`hold ${comparing ? "on" : ""}`}
                title="Hold to compare the scene before development"
                onPointerDown={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  holdCompare(true);
                }}
                onPointerUp={(event) => {
                  event.stopPropagation();
                  holdCompare(false);
                }}
                onPointerLeave={() => holdCompare(false)}
                onPointerCancel={() => holdCompare(false)}
              >
                <CompareIcon />
                Hold
              </button>
            ) : null}
            <p className="rebate">
              <span className="rebate-id">SF</span>
              <span className="name">{captionFor(preview, sourceMode, rawPath, imagePath)}</span>
              {stale ? (
                <span className="stale" title="The easel does not match the controls">
                  Stale
                </span>
              ) : preview ? (
                <span className="fresh" title="The easel matches the controls" />
              ) : null}
            </p>
          </div>
          {frames.length > 0 ? (
            <div className="roll" role="list" aria-label="Recent frames">
              {frames.map((frame) => (
                <button
                  key={frame.id}
                  type="button"
                  className={frame.id === shownId ? "on" : ""}
                  title={`${labelFor(filmTiles, frame.result.film_profile)} · ${labelFor(paperTiles, frame.result.print_profile)}`}
                  onClick={() => {
                    setShownId(frame.id);
                    setPreview(frame.result);
                    setDevelopedKey(frame.key);
                    setComparing(false);
                  }}
                >
                  <img alt="" src={`data:${frame.result.mime};base64,${frame.result.png_base64}`} />
                </button>
              ))}
            </div>
          ) : null}
        </main>

        <div
          className="handle"
          role="separator"
          aria-orientation="vertical"
          aria-valuemin={INSPECTOR_MIN}
          aria-valuemax={INSPECTOR_MAX}
          aria-valuenow={inspectorWidth}
          aria-label="Inspector width"
          tabIndex={0}
          title="Drag to resize. Double-click restores."
          onPointerDown={resizeInspector}
          onDoubleClick={() => setInspectorWidth(INSPECTOR_DEFAULT)}
          onKeyDown={(event) => {
            if (event.key === "ArrowLeft") {
              setInspectorWidth((width) => Math.min(INSPECTOR_MAX, width + 16));
            } else if (event.key === "ArrowRight") {
              setInspectorWidth((width) => Math.max(INSPECTOR_MIN, width - 16));
            } else if (event.key === "Home") {
              setInspectorWidth(INSPECTOR_DEFAULT);
            }
          }}
        />

        <aside className="inspector">
          <p className={`readout ${job.tone}`} title={job.text}>
            {preview
              ? `${preview.width}×${preview.height} · ${(preview.elapsed_ms / 1000).toFixed(1)} s`
              : job.tone === "idle"
                ? "No print"
                : job.text}
          </p>
          {runError ? <p className="error">{runError}</p> : null}
          {bootError && phase !== "ready" ? <p className="error">{bootError}</p> : null}

          <section className="cluster">
            <h2 title="camera.exposure_compensation_ev">Exposure</h2>
            <Slider
              label="EV"
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

          <section className="cluster">
            <h2 title="enlarger.y_filter_shift and enlarger.m_filter_shift">Filters</h2>
            <Slider
              label="Yellow"
              title="enlarger.y_filter_shift, Kodak CC steps from neutral"
              tone="yellow"
              min={-80}
              max={80}
              step={1}
              value={yShift}
              disabled={!shellReady}
              display={signed(yShift, 0)}
              onChange={setYShift}
            />
            <Slider
              label="Magenta"
              title="enlarger.m_filter_shift, Kodak CC steps from neutral"
              tone="magenta"
              min={-80}
              max={80}
              step={1}
              value={mShift}
              disabled={!shellReady}
              display={signed(mShift, 0)}
              onChange={setMShift}
            />
          </section>

          <section className="cluster">
            <h2 title="film_render.halation">Halation</h2>
            <div className="chips" role="group" aria-label="Halation">
              <button
                type="button"
                className={halationActive ? "on" : ""}
                disabled={!shellReady}
                title="film_render.halation.active"
                onClick={() => setHalationActive((active) => !active)}
              >
                {halationActive ? "On" : "Off"}
              </button>
            </div>
            <Slider
              label="Scatter"
              title="film_render.halation.scatter_amount. 1 matches the stock model."
              tone="heat"
              min={0}
              max={2}
              step={0.05}
              value={scatterAmount}
              disabled={!shellReady || !halationActive}
              display={scatterAmount.toFixed(2)}
              onChange={setScatterAmount}
            />
            <Slider
              label="Size"
              title="film_render.halation.scatter_spatial_scale"
              tone="heat"
              min={0}
              max={2}
              step={0.05}
              value={scatterSize}
              disabled={!shellReady || !halationActive}
              display={scatterSize.toFixed(2)}
              onChange={setScatterSize}
            />
            <Slider
              label="Halo"
              title="film_render.halation.halation_amount"
              tone="heat"
              min={0}
              max={2}
              step={0.05}
              value={halationAmount}
              disabled={!shellReady || !halationActive}
              display={halationAmount.toFixed(2)}
              onChange={setHalationAmount}
            />
            <Slider
              label="Reach"
              title="film_render.halation.halation_spatial_scale"
              tone="heat"
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
            <h2 title="settings.preview_mode. Scan still resizes to the long edge below.">Gate</h2>
            <div className="chips" role="group" aria-label="Render mode">
              <button
                type="button"
                className={renderMode === "preview" ? "on" : ""}
                disabled={!shellReady}
                title="settings.preview_mode on. Grain and several blurs are skipped."
                onClick={() => setRenderMode("preview")}
              >
                <EyeIcon />
                Preview
              </button>
              <button
                type="button"
                className={renderMode === "scan" ? "on" : ""}
                disabled={!shellReady}
                title="settings.preview_mode off. Still limited to the long edge below."
                onClick={() => setRenderMode("scan")}
              >
                <ScanIcon />
                Scan
              </button>
            </div>
            <div className="chips" role="group" aria-label="Long edge">
              <button
                type="button"
                className={maxSize === DRAFT_SIZE ? "on" : ""}
                disabled={!shellReady}
                title={`settings.preview_max_size ${DRAFT_SIZE}`}
                onClick={() => setMaxSize(DRAFT_SIZE)}
              >
                {DRAFT_SIZE}
              </button>
              <button
                type="button"
                className={maxSize === FINE_SIZE ? "on" : ""}
                disabled={!shellReady}
                title={`settings.preview_max_size ${FINE_SIZE}`}
                onClick={() => setMaxSize(FINE_SIZE)}
              >
                {FINE_SIZE}
              </button>
            </div>
          </section>

          {sourceMode === "file" ? (
            <section>
              <h2 title="load_image_oiio">File</h2>
              <label className="field">
                <span>Path</span>
                <input
                  type="text"
                  value={imagePath}
                  disabled={!shellReady}
                  placeholder="scene_linear.tif"
                  spellCheck={false}
                  onChange={(event) => setImagePath(event.target.value)}
                />
              </label>
            </section>
          ) : null}

          {sourceMode === "raw" ? (
            <section>
              <h2
                title={
                  rawInfo
                    ? `${rawInfo.width}×${rawInfo.height} · ${rawInfo.input_color_space}${rawInfo.lens_summary ? ` · ${rawInfo.lens_summary}` : ""}`
                    : "rawpy import"
                }
              >
                RAW
              </h2>
              <div className="chips wrap" role="group" aria-label="White balance">
                {WHITE_BALANCE_OPTIONS.map((option) => (
                  <button
                    key={option.id}
                    type="button"
                    className={whiteBalance === option.id ? "on" : ""}
                    disabled={!shellReady}
                    title={option.title}
                    onClick={() => setWhiteBalance(option.id)}
                  >
                    {option.label}
                  </button>
                ))}
                <button
                  type="button"
                  className={lensCorrection ? "on" : ""}
                  disabled={!shellReady}
                  title="lensfun correction during RAW import"
                  onClick={() => setLensCorrection((enabled) => !enabled)}
                >
                  Lens
                </button>
              </div>
              <Slider
                label="Kelvin"
                title="Used only for custom white balance"
                tone="kelvin"
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
                tone="magenta"
                min={0.7}
                max={1.3}
                step={0.01}
                value={tint}
                disabled={!shellReady || !customBalance}
                display={tint.toFixed(2)}
                onChange={setTint}
              />
              <label className="field">
                <span>Path</span>
                <input
                  type="text"
                  value={rawPath}
                  disabled={!shellReady}
                  placeholder="frame.nef"
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
                  Reload
                </button>
              </div>
            </section>
          ) : null}
        </aside>
      </div>
    </div>
  );
}

function StockStrip({
  label,
  kind,
  profiles,
  selected,
  disabled,
  thumbs,
  pending,
  onSelect,
}: {
  label: string;
  kind: "film" | "paper";
  profiles: Named[];
  selected: string;
  disabled: boolean;
  thumbs: Record<string, string>;
  pending: boolean;
  onSelect: (id: string) => void;
}) {
  function onKey(event: ReactKeyboardEvent<HTMLButtonElement>) {
    if (disabled || (event.key !== "ArrowLeft" && event.key !== "ArrowRight")) {
      return;
    }
    event.preventDefault();
    const index = Math.max(0, profiles.findIndex((profile) => profile.id === selected));
    const nextIndex =
      event.key === "ArrowRight" ? Math.min(profiles.length - 1, index + 1) : Math.max(0, index - 1);
    const next = profiles[nextIndex];
    if (!next || next.id === selected) {
      return;
    }
    onSelect(next.id);
    const sibling = event.currentTarget.parentElement?.querySelector<HTMLButtonElement>(
      `[data-stock="${CSS.escape(next.id)}"]`,
    );
    sibling?.focus();
    sibling?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }

  return (
    <div className={`strip ${kind}`} role="group" aria-label={label}>
      <span className="strip-label">{label}</span>
      <div className="strip-scroll">
        {profiles.map((profile) => {
          const on = selected === profile.id;
          const thumb = thumbs[profile.id];
          return (
            <button
              key={profile.id}
              type="button"
              className={`tile ${on ? "on" : ""}`}
              data-stock={profile.id}
              disabled={disabled}
              title={profile.name}
              aria-pressed={on}
              tabIndex={disabled ? -1 : on ? 0 : -1}
              onKeyDown={onKey}
              onClick={() => onSelect(profile.id)}
            >
              <span
                className={`swatch ${pending && !thumb ? "pending" : ""}`}
                style={{ background: kind === "film" ? filmSwatch(profile.id) : paperSwatch(profile.id) }}
              >
                {kind === "film" && !thumb ? <i className="chartlet" aria-hidden="true" /> : null}
                {thumb ? <img alt="" src={thumb} /> : null}
              </span>
              <span className="cap">{shortStock(profile.name)}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function StatusPill({ phase, job, title }: { phase: Phase; job: Job; title: string }) {
  const tone = job.tone === "running" ? "booting" : job.tone === "error" ? "error" : phase;
  const label = job.tone === "running" || job.tone === "error" ? job.text : phaseLabel(phase);
  return (
    <p className={`lamp ${tone}`} title={title}>
      <i aria-hidden="true" />
      <span>{label.length > 28 ? `${label.slice(0, 26)}…` : label}</span>
    </p>
  );
}

function DyeMark() {
  return (
    <svg className="mark" viewBox="0 0 34 34" aria-hidden="true">
      <rect width="34" height="34" fill="#100e0c" />
      <path d="M4 26 L17 6 L20 6 L7 26 Z" fill="#6fafa8" />
      <path d="M11 26 L20 8 L23 8 L14 26 Z" fill="#c56b78" />
      <path d="M18 26 L24 12 L27 12 L21 26 Z" fill="#e2b15a" />
      <rect x="4" y="28" width="26" height="2" fill="#f6efe2" opacity="0.85" />
    </svg>
  );
}

function CompareIcon() {
  return (
    <svg className="chip-icon" viewBox="0 0 16 16" aria-hidden="true">
      <rect x="1.5" y="3.5" width="8" height="8" fill="none" stroke="currentColor" strokeWidth="1.2" />
      <rect x="6.5" y="4.5" width="8" height="8" fill="currentColor" opacity="0.35" />
    </svg>
  );
}

function EyeIcon() {
  return (
    <svg className="chip-icon" viewBox="0 0 16 16" aria-hidden="true">
      <path
        d="M1.5 8 C4 4.2 12 4.2 14.5 8 C12 11.8 4 11.8 1.5 8 Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.2"
      />
      <circle cx="8" cy="8" r="1.6" fill="currentColor" />
    </svg>
  );
}

function ScanIcon() {
  return (
    <svg className="chip-icon" viewBox="0 0 16 16" aria-hidden="true">
      <rect x="2" y="2" width="5" height="5" fill="currentColor" />
      <rect x="9" y="2" width="5" height="5" fill="currentColor" opacity="0.45" />
      <rect x="2" y="9" width="5" height="5" fill="currentColor" opacity="0.45" />
      <rect x="9" y="9" width="5" height="5" fill="currentColor" />
    </svg>
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
  tone = "neutral",
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
  tone?: "neutral" | "yellow" | "magenta" | "heat" | "kelvin";
}) {
  const span = max - min;
  const pct = span === 0 ? 0 : ((value - min) / span) * 100;
  const ink =
    tone === "magenta" ? "#c56b78" : tone === "heat" ? "#d07a62" : tone === "yellow" ? "#e2b15a" : "#c9964a";
  return (
    <label className={`field ${disabled ? "is-off" : ""}`}>
      <span className="split" title={title}>
        <span>{label}</span>
        <span className="value">{display}</span>
      </span>
      <input
        type="range"
        className={tone === "kelvin" ? "tone-kelvin" : undefined}
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        aria-label={label}
        style={{ ["--fill" as string]: `${pct}%`, ["--ink" as string]: ink }}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

function EmptyStage() {
  const holes = Array.from({ length: 14 }, (_, index) => 16 + index * 21);
  return (
    <div className="empty">
      <svg className="gate-drawing" viewBox="0 0 320 180" aria-hidden="true">
        <rect width="320" height="180" fill="#0c0b09" />
        {holes.map((x) => (
          <rect key={`t${x}`} x={x} y="6" width="8" height="6" rx="1" fill="#241e18" />
        ))}
        {holes.map((x) => (
          <rect key={`b${x}`} x={x} y="168" width="8" height="6" rx="1" fill="#241e18" />
        ))}
        <rect x="36" y="28" width="248" height="124" fill="#070605" stroke="#3a322a" />
        <rect x="248" y="28" width="36" height="124" fill="url(#fog)" />
        <defs>
          <linearGradient id="fog" x1="0" x2="1">
            <stop offset="0" stopColor="#6fafa8" stopOpacity="0" />
            <stop offset="0.45" stopColor="#6fafa8" stopOpacity="0.45" />
            <stop offset="0.72" stopColor="#c56b78" stopOpacity="0.4" />
            <stop offset="1" stopColor="#e2b15a" stopOpacity="0.7" />
          </linearGradient>
        </defs>
      </svg>
      <p>Unexposed</p>
    </div>
  );
}

function phaseLabel(phase: Phase): string {
  switch (phase) {
    case "booting":
      return "Starting";
    case "ready":
      return "Ready";
    case "offline":
      return "Offline";
    case "error":
      return "Sidecar error";
  }
}

function formatEv(value: number): string {
  const rounded = Math.round(value * 10) / 10;
  const text = rounded.toFixed(1);
  return rounded > 0 ? `+${text}` : text;
}

function signed(value: number, digits: number): string {
  const text = value.toFixed(digits);
  return value > 0 ? `+${text}` : text;
}

function shortStock(name: string): string {
  return name
    .replace(/^Kodak Professional\s+/i, "")
    .replace(/^Kodak\s+/i, "")
    .replace(/^Fujifilm\s+/i, "")
    .replace(/\s+/g, " ")
    .trim();
}

function labelFor(profiles: Named[], id: string): string {
  return profiles.find((profile) => profile.id === id)?.name ?? id;
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
    return fileName(preview.image_path ?? imagePath);
  }
  if (preview) {
    return "Color chart";
  }
  if (sourceMode === "raw" && rawPath.trim()) {
    return fileName(rawPath);
  }
  if (sourceMode === "file" && imagePath.trim()) {
    return fileName(imagePath);
  }
  return "No print";
}
