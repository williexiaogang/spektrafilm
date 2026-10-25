# Pipeline regression baselines

`tests/regression_baselines.py` defines the deterministic input recipes and
parameters. Spatial and stochastic effects, auto exposure, and enlarger/scanner
LUT interpolation are disabled for these snapshots. The default output gamut
compression remains enabled, so a deliberate change to that default changes the
three final-RGB snapshots.

The RGB snapshots were refreshed on 2026-10-25 for the existing CAM16-UCS default
and black-anchored, one-sided lightness compression. The previous snapshots were
last changed in `ac16d86` and used Oklch plus the earlier two-sided lightness knee.
Subsequent gamut-compression changes (`eac6b85`, `6ec371b`, and the later default
selection) had not been reflected in these files.

Before refreshing, the output compression code and defaults from `ac16d86` were
substituted into the current pipeline in an isolated diagnostic process. All
five original snapshots matched, with maximum absolute errors below `2.3e-15`.
This isolates the drift to the intentional output-compression changes rather
than the input profiles, exposure, film development, or machine precision.

Only these three snapshots were updated:

- `print_rgb_portra_endura_gray_ramp16.npz`
- `print_rgb_fuji_crystal_gray_ramp16.npz`
- `print_rgb_portra_endura_green_patch8.npz`

The `log_e_film` and `cmy_film` snapshots remain unchanged. Do not regenerate
baselines solely to make failing tests pass: first isolate and document the
intended numerical change. Tests for gamut compression separately guard black
anchoring, valid ranges, and the compression behavior.
