import numpy as np
import pytest

from spektrafilm.profiles.io import Hanatos2025SensitivityAdaptation
from spektrafilm.runtime.services import spectral_lut_compute as spectral_lut_compute_module


pytestmark = pytest.mark.unit

@pytest.mark.parametrize("stage", ["enlarger", "scanner"])
@pytest.mark.parametrize("bound", ["min", "max"])
def test_cached_lut_is_rebuilt_when_its_sampling_domain_changes(stage, bound):
    service = spectral_lut_compute_module.SpectralLUTService(lut_resolution=5)
    compute = getattr(service, f"spectral_compute_{stage}")
    data = np.full((1, 1, 3), 0.5)
    data_min = np.zeros(3)
    data_max = np.ones(3)
    identity = lambda image: image
    compute(data, identity, data_min, data_max, use_lut=True)
    original_lut = getattr(service, f"{stage}_lut_memory")

    # Equivalent arrays can reuse the table; changing the original arrays
    # in place must not mutate the cached domain snapshot.
    compute(data, identity, data_min.copy(), data_max.copy(), use_lut=True)
    assert getattr(service, f"{stage}_lut_memory") is original_lut
    if bound == "max":
        data_max[:] = [2.0, 3.0, 4.0]
    else:
        data_min[:] = [-1.0, -2.0, -3.0]
    actual = compute(data, identity, data_min, data_max, use_lut=True)
    fresh = getattr(spectral_lut_compute_module.SpectralLUTService(5), f"spectral_compute_{stage}")(
        data, identity, data_min, data_max, use_lut=True,
    )
    assert getattr(service, f"{stage}_lut_memory") is not original_lut
    np.testing.assert_allclose(actual, fresh, atol=1e-12)
    np.testing.assert_allclose(actual, data, atol=1e-12)


def test_filming_tc_lut_recomputes_when_spectral_gaussian_blur_changes(monkeypatch) -> None:
    calls: list[float] = []

    def fake_compute_hanatos2025_tc_lut(sensitivity, adaptation, gamut_compress=None):
        del sensitivity, gamut_compress
        calls.append(float(adaptation.spectral_gaussian_blur))
        return np.full((2, 2, 3), adaptation.spectral_gaussian_blur + 1.0, dtype=float)

    monkeypatch.setattr(
        spectral_lut_compute_module,
        'compute_hanatos2025_tc_lut',
        fake_compute_hanatos2025_tc_lut,
    )

    service = spectral_lut_compute_module.SpectralLUTService(lut_resolution=17)
    sensitivity = np.ones((4, 3), dtype=float)
    adaptation = Hanatos2025SensitivityAdaptation(
        window_params=np.empty((0,), dtype=float),
        surface_params=np.empty((0, 3), dtype=float),
        spectral_gaussian_blur=0.0,
        reference_illuminant='D55',
        apply_window=True,
        apply_surface=True,
    )

    service.set_hanatos2025_adaptation(adaptation)
    first = service.get_filming_tc_lut(sensitivity)

    adaptation.spectral_gaussian_blur = 4.0
    service.set_hanatos2025_adaptation(adaptation)
    second = service.get_filming_tc_lut(sensitivity)

    assert calls == [0.0, 4.0]
    assert np.array_equal(first, second) is False
