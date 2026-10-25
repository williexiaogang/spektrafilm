import numpy as np
import pytest

from spektrafilm.utils.fast_stats import fast_binomial


@pytest.mark.parametrize("probability", [0.001, 0.999])
def test_binomial_small_variance_tails_keep_their_mean_and_variance(probability):
    count = np.full(32768, 1000, dtype=np.int64)
    probabilities = np.full(count.shape, probability)
    samples = fast_binomial(count, probabilities)
    assert samples.min() >= 0
    assert samples.max() <= 1000
    assert abs(samples.mean() - 1000 * probability) < 0.05
    assert abs(samples.var() - 1000 * probability * (1 - probability)) < 0.06


def test_binomial_boundary_probabilities_and_zero_trials():
    count = np.array([0, 100, 100], dtype=np.int64)
    probability = np.array([0.5, 0.0, 1.0])
    np.testing.assert_array_equal(fast_binomial(count, probability), [0, 0, 100])
