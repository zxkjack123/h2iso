"""Tests for h2iso.uq.__init__ — top-level UQStudy / ParameterSpace API."""

import numpy as np

from h2iso.uq import Parameter, ParameterSpace, UQStudy, qoi_default


class TestParameterSpace:
    def test_from_list(self):
        params = [
            Parameter("R", "normal", {"mu": 15, "sigma": 0.3}),
            Parameter("F", "uniform", {"low": 70, "high": 90}),
        ]
        space = ParameterSpace.from_list(params)
        assert space.n_params == 2
        assert space.names == ["R", "F"]

    def test_from_dicts(self):
        dicts = [
            {"name": "R", "distribution": "normal", "params": {"mu": 15, "sigma": 0.3}},
            {
                "name": "P",
                "distribution": "uniform",
                "params": {"low": 80000, "high": 100000},
            },
        ]
        space = ParameterSpace.from_dicts(dicts)
        assert space.n_params == 2
        assert space.names == ["R", "P"]

    def test_to_dict(self):
        params = [Parameter("R", "normal", {"mu": 15, "sigma": 0.3})]
        space = ParameterSpace.from_list(params)
        d = space.to_dict()
        assert "parameters" in d
        assert d["parameters"][0]["name"] == "R"


class TestUQStudyAPI:
    def test_creation(self):
        space = ParameterSpace.from_list(
            [
                Parameter("R", "normal", {"mu": 15, "sigma": 0.3}),
            ]
        )
        study = UQStudy(
            build_fn=lambda p: None,
            parameter_space=space,
        )
        assert study.qoi_fn is qoi_default
        assert len(study.qoi_names) == 16  # 2*6 + 4

    def test_custom_qoi_fn(self):
        space = ParameterSpace.from_list(
            [
                Parameter("R", "normal", {"mu": 15, "sigma": 0.3}),
            ]
        )
        custom_qoi = lambda r: np.array([1.0])  # noqa: E731
        study = UQStudy(
            build_fn=lambda p: None,
            parameter_space=space,
            qoi_fn=custom_qoi,
            qoi_names=["custom"],
        )
        assert study.qoi_fn is custom_qoi
        assert study.qoi_names == ["custom"]
