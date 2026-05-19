"""Tests for Stream data structure and operations (Task 2.1.1)."""

import numpy as np
import pytest

from h2iso.flowsheet.stream import Stream, stream_mix, stream_split
from h2iso.species import N_SPECIES


@pytest.fixture
def h2_stream():
    """Pure H2 stream."""
    z = np.zeros(N_SPECIES)
    z[0] = 1.0
    return Stream(flow=100.0, composition=z, temperature=20.0, pressure=101325.0)


@pytest.fixture
def d2_stream():
    """Pure D2 stream."""
    z = np.zeros(N_SPECIES)
    z[3] = 1.0
    return Stream(flow=50.0, composition=z, temperature=24.0, pressure=101325.0)


class TestStream:
    """Test Stream dataclass."""

    def test_creation(self, h2_stream):
        assert h2_stream.flow == 100.0
        assert h2_stream.temperature == 20.0
        assert h2_stream.phase == "liquid"
        assert h2_stream.composition[0] == 1.0

    def test_invalid_composition_shape(self):
        with pytest.raises(ValueError, match="shape"):
            Stream(flow=10.0, composition=np.array([0.5, 0.5]), temperature=20.0, pressure=101325.0)


class TestStreamMix:
    """Test stream_mix()."""

    def test_two_streams_mass_conservation(self, h2_stream, d2_stream):
        mixed = stream_mix([h2_stream, d2_stream])
        # Total flow conserved
        assert mixed.flow == pytest.approx(150.0)
        # Component flows conserved
        np.testing.assert_allclose(
            mixed.flow * mixed.composition[0],
            h2_stream.flow * h2_stream.composition[0],
            rtol=1e-10,
        )
        np.testing.assert_allclose(
            mixed.flow * mixed.composition[3],
            d2_stream.flow * d2_stream.composition[3],
            rtol=1e-10,
        )

    def test_composition_sums_to_one(self, h2_stream, d2_stream):
        mixed = stream_mix([h2_stream, d2_stream])
        np.testing.assert_allclose(mixed.composition.sum(), 1.0, atol=1e-12)

    def test_temperature_flow_weighted(self, h2_stream, d2_stream):
        mixed = stream_mix([h2_stream, d2_stream])
        expected_T = (100.0 * 20.0 + 50.0 * 24.0) / 150.0
        assert mixed.temperature == pytest.approx(expected_T)

    def test_single_stream(self, h2_stream):
        mixed = stream_mix([h2_stream])
        assert mixed.flow == h2_stream.flow
        np.testing.assert_array_equal(mixed.composition, h2_stream.composition)

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            stream_mix([])


class TestStreamSplit:
    """Test stream_split()."""

    def test_equal_split(self, h2_stream):
        parts = stream_split(h2_stream, [1.0, 1.0])
        assert len(parts) == 2
        assert parts[0].flow == pytest.approx(50.0)
        assert parts[1].flow == pytest.approx(50.0)
        np.testing.assert_array_equal(parts[0].composition, h2_stream.composition)

    def test_unequal_split(self, h2_stream):
        parts = stream_split(h2_stream, [3.0, 1.0])
        assert parts[0].flow == pytest.approx(75.0)
        assert parts[1].flow == pytest.approx(25.0)

    def test_mass_conservation(self, h2_stream):
        parts = stream_split(h2_stream, [2.0, 3.0, 5.0])
        total = sum(p.flow for p in parts)
        assert total == pytest.approx(h2_stream.flow)

    def test_empty_ratios_raises(self, h2_stream):
        with pytest.raises(ValueError, match="non-empty"):
            stream_split(h2_stream, [])


class TestStreamInputValidation:
    """Task 4.1: Stream rejects invalid composition at construction."""

    def test_negative_composition_rejected(self):
        bad = np.array([-0.1, 0.0, 0.0, 1.1, 0.0, 0.0])
        with pytest.raises(ValueError, match="non-negative"):
            Stream(flow=1.0, composition=bad, temperature=25.0, pressure=101325.0)

    def test_unnormalized_composition_rejected(self):
        bad = np.array([0.5, 0.0, 0.0, 0.4, 0.0, 0.0])  # sum=0.9
        with pytest.raises(ValueError, match="sum to 1"):
            Stream(flow=1.0, composition=bad, temperature=25.0, pressure=101325.0)

    def test_oversum_composition_rejected(self):
        bad = np.array([0.6, 0.0, 0.0, 0.6, 0.0, 0.0])  # sum=1.2
        with pytest.raises(ValueError, match="sum to 1"):
            Stream(flow=1.0, composition=bad, temperature=25.0, pressure=101325.0)

    def test_round_off_composition_accepted(self):
        """NLP solver noise within tolerance must not be rejected."""
        comp = np.array([1.0 - 1e-9, -1e-10, 0.0, 1e-9, 0.0, 0.0])
        # Should not raise
        s = Stream(flow=1.0, composition=comp, temperature=25.0, pressure=101325.0)
        assert s.composition.shape == (N_SPECIES,)
