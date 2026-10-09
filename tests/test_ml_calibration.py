"""Tests for Batch C: classical ML backends + calibration (slices 21-30)."""

from __future__ import annotations

import numpy as np
import pytest

from hugrgate.backends.boosting import GradientBoostingBackend
from hugrgate.backends.forest import RandomForestBackend
from hugrgate.backends.logreg import LogisticRegressionBackend
from hugrgate.calibration import (
    CalibratorRegistry,
    IsotonicCalibrator,
    PlattCalibrator,
    TemperatureCalibrator,
)
from hugrgate.calibration.metrics import (
    brier_score,
    ece_multiclass,
    expected_calibration_error,
    log_loss,
    maximum_calibration_error,
    reliability_diagram,
)
from hugrgate.calibration.profiles import (
    CalibratedBackend,
    CalibrationProfile,
    CalibrationProfileStore,
    hash_dataset,
)
from hugrgate.errors import BackendError, CalibrationError, HugrGateError
from hugrgate.features import (
    CategoricalEncoder,
    FeatureExtractor,
    MissingValuePolicy,
    NumericEncoder,
    Pipeline,
    TextLengthEncoder,
)
from hugrgate.models import ModelManifest, ModelStore
from hugrgate.spec import DecisionSpec


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _toy_states(n: int = 60, seed: int = 0):
    rng = np.random.default_rng(seed)
    states, labels = [], []
    for _ in range(n):
        x = float(rng.normal())
        s = {"x": x, "color": rng.choice(["red", "blue"]),
             "note": "hello world" if x > 0 else "hi"}
        states.append(s)
        labels.append("pos" if x + rng.normal(0, 0.3) > 0 else "neg")
    return states, labels


def _pipeline():
    return Pipeline([
        NumericEncoder(["x"]),
        CategoricalEncoder("color"),
        TextLengthEncoder("note"),
    ])


def _trained_logreg(seed: int = 0):
    states, labels = _toy_states(seed=seed)
    be = LogisticRegressionBackend("toy", _pipeline(), C=1.0)
    be.train(list(zip(states, labels)))
    return be, states, labels


SPEC = DecisionSpec(type="categorical", options=["neg", "pos"])


# ---------------------------------------------------------------------------
# Slice 21: features
# ---------------------------------------------------------------------------

class TestNumericEncoder:
    def test_extract(self):
        enc = NumericEncoder(["a", "b"])
        assert enc.extract({"a": 1, "b": 2.5}) == {"a": 1.0, "b": 2.5}

    def test_bool_coerced(self):
        enc = NumericEncoder(["a"])
        assert enc.extract({"a": True}) == {"a": 1.0}

    def test_missing_zero(self):
        enc = NumericEncoder(["a"])
        assert enc.extract({}) == {"a": 0.0}

    def test_missing_mean(self):
        enc = NumericEncoder(["a"], missing=MissingValuePolicy.MEAN)
        enc.fit([{"a": 2.0}, {"a": 4.0}, {}])
        assert enc.extract({}) == {"a": 3.0}

    def test_missing_error(self):
        enc = NumericEncoder(["a"], missing=MissingValuePolicy.ERROR)
        with pytest.raises(BackendError):
            enc.extract({})

    def test_non_numeric_uses_policy(self):
        enc = NumericEncoder(["a"])
        assert enc.extract({"a": "junk"}) == {"a": 0.0}


class TestCategoricalEncoder:
    def test_one_hot(self):
        enc = CategoricalEncoder("color", categories=["blue", "red"])
        out = enc.extract({"color": "red"})
        assert out == {"color__blue": 0.0, "color__red": 1.0}

    def test_fit_infers_sorted(self):
        enc = CategoricalEncoder("color").fit([{"color": "b"}, {"color": "a"}])
        assert enc.categories == ["a", "b"]
        assert enc.feature_names() == ["color__a", "color__b"]

    def test_unknown_ignored(self):
        enc = CategoricalEncoder("color", categories=["red"])
        out = enc.extract({"color": "green"})
        assert out == {"color__red": 0.0}

    def test_unknown_error(self):
        enc = CategoricalEncoder("color", categories=["red"],
                                 handle_unknown="error")
        with pytest.raises(BackendError):
            enc.extract({"color": "green"})

    def test_unfitted_raises(self):
        with pytest.raises(BackendError):
            CategoricalEncoder("color").extract({"color": "red"})


class TestTextLengthEncoder:
    def test_lengths(self):
        enc = TextLengthEncoder("note")
        out = enc.extract({"note": "hello world"})
        assert out == {"note__len": 11.0, "note__words": 2.0}

    def test_missing_is_empty(self):
        enc = TextLengthEncoder("note")
        assert enc.extract({})["note__len"] == 0.0


class TestPipeline:
    def test_composition(self):
        pipe = _pipeline().fit(_toy_states()[0])
        names = pipe.feature_names()
        assert names == ["x", "color__blue", "color__red",
                         "note__len", "note__words"]
        out = pipe.extract({"x": 1.0, "color": "red", "note": "ab cd"})
        assert out["x"] == 1.0 and out["color__red"] == 1.0
        assert out["note__words"] == 2.0

    def test_transform_batch_shape(self):
        states, _ = _toy_states()
        pipe = _pipeline().fit(states)
        X = pipe.transform_batch(states)
        assert X.shape == (len(states), len(pipe.feature_names()))

    def test_duplicate_names_rejected(self):
        pipe = Pipeline([NumericEncoder(["x"]), NumericEncoder(["x"])])
        with pytest.raises(BackendError):
            pipe.fit([{"x": 1.0}])

    def test_extractor_interface(self):
        assert isinstance(_pipeline(), FeatureExtractor)


# ---------------------------------------------------------------------------
# Slices 22-24: ML backends
# ---------------------------------------------------------------------------

class TestLogregBackend:
    def test_train_evaluate(self):
        be, states, _ = _trained_logreg()
        assert be.is_trained
        result = be.evaluate(states[0], SPEC)
        assert result.value in ("neg", "pos")
        assert abs(sum(result.distribution.values()) - 1.0) < 1e-6
        assert result.probability == result.distribution[result.value]
        assert result.backend == "logreg"
        assert result.latency_ms >= 0

    def test_supports(self):
        be, _, _ = _trained_logreg()
        assert be.supports(SPEC)
        # trained on {"neg","pos"}: binary value space is {"true","false"}
        assert not be.supports(DecisionSpec(type="binary", statement="s"))
        assert not be.supports(DecisionSpec(type="ordinal",
                                            levels=["a", "b"]))
        # wrong class set -> no support
        other = DecisionSpec(type="categorical", options=["x", "y"])
        assert not be.supports(other)
        # untrained backend accepts any supported spec type
        fresh = LogisticRegressionBackend("fresh", _pipeline())
        assert fresh.supports(SPEC)
        assert fresh.supports(DecisionSpec(type="binary", statement="s"))

    def test_untrained_raises(self):
        be = LogisticRegressionBackend("u", _pipeline())
        with pytest.raises(Exception):
            be.evaluate({"x": 1.0, "color": "red", "note": "hi"}, SPEC)

    def test_train_needs_two_classes(self):
        be = LogisticRegressionBackend("u", _pipeline())
        states, _ = _toy_states()
        with pytest.raises(BackendError):
            be.train([(s, "neg") for s in states[:5]])

    def test_save_load_roundtrip(self, tmp_path):
        be, states, _ = _trained_logreg()
        path = str(tmp_path / "model.pkl")
        be.save(path)
        loaded = LogisticRegressionBackend.load(path)
        for s in states[:10]:
            a = be.predict_proba_dict(s)
            b = loaded.predict_proba_dict(s)
            assert a.keys() == b.keys()
            for k in a:
                assert abs(a[k] - b[k]) < 1e-9

    def test_capabilities(self):
        be = LogisticRegressionBackend("u", _pipeline())
        caps = be.capabilities()
        assert caps["trainable"] and caps["predict_proba"]
        assert "categorical" in caps["spec_types"]

    def test_binary_spec(self):
        states, labels = _toy_states()
        blabels = ["true" if l == "pos" else "false" for l in labels]
        be = LogisticRegressionBackend("b", _pipeline())
        be.train(list(zip(states, blabels)))
        spec = DecisionSpec(type="binary", statement="positive?")
        r = be.evaluate(states[0], spec)
        assert r.value in ("true", "false")
        assert set(r.distribution) == {"true", "false"}


class TestForestBackend:
    def _trained(self):
        states, labels = _toy_states(n=120, seed=1)
        be = RandomForestBackend("toy-f", _pipeline())
        be.train(list(zip(states, labels)))
        return be, states

    def test_contract_parity(self):
        be, states = self._trained()
        r = be.evaluate(states[0], SPEC)
        assert abs(sum(r.distribution.values()) - 1.0) < 1e-6
        assert r.value in ("neg", "pos")
        assert be.supports(SPEC)

    def test_feature_importances(self):
        be, states = self._trained()
        r = be.evaluate(states[0], SPEC)
        imp = r.metadata["feature_importances"]
        assert abs(sum(imp.values()) - 1.0) < 1e-6
        assert set(imp) == set(be._pipeline.feature_names())

    def test_save_load(self, tmp_path):
        be, states = self._trained()
        path = str(tmp_path / "f.pkl")
        be.save(path)
        loaded = RandomForestBackend.load(path)
        assert loaded.is_trained
        assert loaded.name == "forest"


class TestBoostingBackend:
    def test_contract_parity(self):
        states, labels = _toy_states(n=300, seed=2)
        be = GradientBoostingBackend("toy-b", _pipeline())
        be.train(list(zip(states, labels)))
        r = be.evaluate(states[0], SPEC)
        assert abs(sum(r.distribution.values()) - 1.0) < 1e-6
        assert r.value in ("neg", "pos")

    def test_early_stopping_config(self):
        be = GradientBoostingBackend("e", _pipeline(), early_stopping=False)
        assert be.capabilities()["early_stopping"] is False

    def test_save_load(self, tmp_path):
        states, labels = _toy_states(n=300, seed=2)
        be = GradientBoostingBackend("toy-b", _pipeline(),
                                     early_stopping=False)
        be.train(list(zip(states, labels)))
        path = str(tmp_path / "b.pkl")
        be.save(path)
        loaded = GradientBoostingBackend.load(path)
        assert loaded.is_trained


# ---------------------------------------------------------------------------
# Slice 25: models
# ---------------------------------------------------------------------------

class TestModelManifest:
    def test_roundtrip(self):
        m = ModelManifest(name="m", version="1.0", backend="logreg",
                          spec_type="categorical", features=["x"],
                          classes=["a", "b"],
                          metrics={"train_accuracy": 0.9})
        m2 = ModelManifest.from_json(m.to_json())
        assert m2.to_dict() == m.to_dict()

    def test_verify_ok_and_tampered(self):
        m = ModelManifest(name="m", version="1.0", backend="logreg",
                          spec_type="categorical", features=[], classes=["a"])
        payload = b"weights-bytes"
        m.payload_hash = hash_payload(payload)
        m.verify(payload)
        with pytest.raises(HugrGateError):
            m.verify(b"tampered")


def hash_payload(payload: bytes) -> str:
    from hugrgate.models import sha256_bytes
    return sha256_bytes(payload)


class TestModelStore:
    def test_put_get(self, tmp_path):
        store = ModelStore(tmp_path / "store")
        m = ModelManifest(name="m", version="1.0.0", backend="logreg",
                          spec_type="categorical", features=["x"],
                          classes=["a", "b"])
        payload = b"\x00\x01\x02"
        store.put(m, payload)
        got, data = store.get("m")
        assert data == payload
        assert got.payload_hash == m.payload_hash
        assert store.list_versions("m") == ["1.0.0"]
        assert store.latest_version("m") == "1.0.0"

    def test_versioned(self, tmp_path):
        store = ModelStore(tmp_path)
        for v in ("1.0.0", "2.0.0"):
            m = ModelManifest(name="m", version=v, backend="logreg",
                              spec_type="categorical", features=[],
                              classes=["a"])
            store.put(m, f"payload-{v}".encode())
        assert store.list_versions("m") == ["1.0.0", "2.0.0"]
        _, data = store.get("m")  # latest
        assert data == b"payload-2.0.0"

    def test_tamper_detected(self, tmp_path):
        store = ModelStore(tmp_path)
        m = ModelManifest(name="m", version="1.0.0", backend="logreg",
                          spec_type="categorical", features=[], classes=["a"])
        vdir = store.put(m, b"good")
        (vdir / ModelStore.PAYLOAD_FILE).write_bytes(b"evil")
        with pytest.raises(HugrGateError):
            store.get("m")

    def test_missing_raises(self, tmp_path):
        store = ModelStore(tmp_path)
        with pytest.raises(HugrGateError):
            store.get("nope")


# ---------------------------------------------------------------------------
# Slices 26-27: calibrators
# ---------------------------------------------------------------------------

def _miscalibrated(n: int = 2000, seed: int = 0):
    """Overconfident scores vs. true labels."""
    rng = np.random.default_rng(seed)
    true_p = rng.uniform(0.05, 0.95, n)
    # overconfident: push toward extremes
    scores = np.clip(0.5 + 1.6 * (true_p - 0.5), 0.01, 0.99)
    labels = (rng.uniform(0, 1, n) < true_p).astype(int)
    return scores, labels


class TestPlatt:
    def test_improves_brier(self):
        scores, labels = _miscalibrated()
        before = brier_score(labels, scores)
        cal = PlattCalibrator().fit(scores, labels)
        after = brier_score(labels, cal.calibrate_batch(scores))
        assert after < before

    def test_bounds(self):
        scores, labels = _miscalibrated()
        cal = PlattCalibrator().fit(scores, labels)
        for s in (-5.0, 0.0, 0.5, 1.0, 5.0):
            assert 0.0 <= cal.calibrate(s) <= 1.0

    def test_params_roundtrip(self):
        scores, labels = _miscalibrated()
        cal = PlattCalibrator().fit(scores, labels)
        cal2 = PlattCalibrator.from_params(cal.get_params())
        assert cal2.calibrate(0.7) == pytest.approx(cal.calibrate(0.7))

    def test_single_class_raises(self):
        with pytest.raises(CalibrationError):
            PlattCalibrator().fit([0.1, 0.2], [0, 0])

    def test_unfitted_raises(self):
        with pytest.raises(CalibrationError):
            PlattCalibrator().calibrate(0.5)

    def test_registered(self):
        assert CalibratorRegistry.get("platt") is PlattCalibrator


class TestIsotonic:
    def test_improves_brier(self):
        scores, labels = _miscalibrated()
        before = brier_score(labels, scores)
        cal = IsotonicCalibrator().fit(scores, labels)
        after = brier_score(labels, cal.calibrate_batch(scores))
        assert after < before

    def test_monotone(self):
        scores, labels = _miscalibrated()
        cal = IsotonicCalibrator().fit(scores, labels)
        grid = np.linspace(0, 1, 50)
        vals = cal.calibrate_batch(grid)
        assert np.all(np.diff(vals) >= -1e-12)

    def test_out_of_range_clamped(self):
        scores, labels = _miscalibrated()
        cal = IsotonicCalibrator().fit(scores, labels)
        assert 0.0 <= cal.calibrate(-10.0) <= 1.0
        assert 0.0 <= cal.calibrate(10.0) <= 1.0

    def test_params_roundtrip(self):
        scores, labels = _miscalibrated()
        cal = IsotonicCalibrator().fit(scores, labels)
        cal2 = IsotonicCalibrator.from_params(cal.get_params())
        assert cal2.calibrate(0.3) == pytest.approx(cal.calibrate(0.3))


class TestTemperature:
    def test_improves_log_loss(self):
        scores, labels = _miscalibrated()
        before = log_loss(labels, scores)
        cal = TemperatureCalibrator().fit(scores, labels)
        after = log_loss(labels, cal.calibrate_batch(scores))
        assert after < before
        assert cal.temperature > 0

    def test_preserves_ranking(self):
        scores, labels = _miscalibrated()
        cal = TemperatureCalibrator().fit(scores, labels)
        grid = np.linspace(0.01, 0.99, 40)
        vals = cal.calibrate_batch(grid)
        assert np.all(np.diff(vals) > 0)  # strictly increasing

    def test_overconfident_cools(self):
        scores, labels = _miscalibrated()
        cal = TemperatureCalibrator().fit(scores, labels)
        # overconfident scores need T > 1 to soften them
        assert cal.temperature > 1.0

    def test_params_roundtrip(self):
        scores, labels = _miscalibrated()
        cal = TemperatureCalibrator().fit(scores, labels)
        cal2 = TemperatureCalibrator.from_params(cal.get_params())
        assert cal2.temperature == pytest.approx(cal.temperature)


# ---------------------------------------------------------------------------
# Slice 28: metrics
# ---------------------------------------------------------------------------

class TestMetrics:
    def test_brier_known(self):
        assert brier_score([0, 1], [0.25, 0.75]) == pytest.approx(0.0625)

    def test_brier_perfect_zero(self):
        assert brier_score([0, 1, 1], [0.0, 1.0, 1.0]) == pytest.approx(0.0)

    def test_log_loss_known(self):
        assert log_loss([0, 1], [0.25, 0.75]) == pytest.approx(
            -np.log(0.75))

    def test_ece_perfect_zero(self):
        y = [0] * 50 + [1] * 50
        p = [0.0] * 50 + [1.0] * 50
        assert expected_calibration_error(y, p) == pytest.approx(0.0)

    def test_ece_known(self):
        # one bin [0.5,1): conf=0.75, acc=0.5 -> gap 0.25 over all N
        y = [1, 1, 0, 0]
        p = [0.75, 0.75, 0.75, 0.75]
        assert expected_calibration_error(y, p, n_bins=2) == pytest.approx(
            0.25)

    def test_mce(self):
        y = [1, 1, 0, 0]
        p = [0.75, 0.75, 0.75, 0.75]
        assert maximum_calibration_error(y, p, n_bins=2) == pytest.approx(
            0.25)

    def test_reliability_diagram(self):
        y = [0, 0, 1, 1]
        p = [0.1, 0.2, 0.8, 0.9]
        bins = reliability_diagram(y, p, n_bins=2)
        assert len(bins) == 2
        assert bins[0]["count"] == 2 and bins[1]["count"] == 2
        assert bins[0]["mean_actual"] == pytest.approx(0.0)
        assert bins[1]["mean_actual"] == pytest.approx(1.0)
        assert abs(sum(b["fraction"] for b in bins) - 1.0) < 1e-9

    def test_ece_multiclass(self):
        y = ["a", "b", "a"]
        probas = [{"a": 0.9, "b": 0.1}, {"a": 0.9, "b": 0.1},
                  {"a": 0.2, "b": 0.8}]
        ece = ece_multiclass(y, probas, n_bins=5)
        assert 0.0 <= ece <= 1.0

    def test_bad_inputs(self):
        with pytest.raises(ValueError):
            brier_score([0, 1], [0.5])
        with pytest.raises(ValueError):
            brier_score([0, 2], [0.5, 0.5])


# ---------------------------------------------------------------------------
# Slice 29: profiles
# ---------------------------------------------------------------------------

def _profile_for(backend) -> CalibrationProfile:
    states, labels = _toy_states(n=200, seed=3)
    raw = [backend.predict_proba_dict(s) for s in states]
    params, scores_all, labels_all = {}, [], []
    for cls in ("neg", "pos"):
        scores = [d[cls] for d in raw]
        labs = [1 if l == cls else 0 for l in labels]
        params[cls] = PlattCalibrator().fit(scores, labs).get_params()
        scores_all.extend(scores)
        labels_all.extend(labs)
    return CalibrationProfile(
        name="toy-platt", version="1.0.0", backend_name=backend.name,
        model_name="toy", model_version="1.0.0", calibrator_name="platt",
        calibrator_params=params,
        metrics={"brier": 0.1},
        dataset_hash=hash_dataset(scores_all, labels_all),
        n_samples=len(states))


class TestCalibrationProfile:
    def test_build_calibrators(self):
        be, _, _ = _trained_logreg()
        prof = _profile_for(be)
        cals = prof.build_calibrators()
        assert set(cals) == {"neg", "pos"}
        assert all(c.fitted for c in cals.values())

    def test_bad_calibrator_name(self):
        with pytest.raises(CalibrationError):
            CalibrationProfile(name="x", calibrator_name="nope")

    def test_store_roundtrip(self, tmp_path):
        be, _, _ = _trained_logreg()
        prof = _profile_for(be)
        store = CalibrationProfileStore(tmp_path)
        store.save(prof)
        got = store.get("toy-platt")
        assert got.to_dict() == prof.to_dict()
        assert got.qualified_name() == "toy-platt@1.0.0"
        assert store.list_versions("toy-platt") == ["1.0.0"]

    def test_store_duplicate_rejected(self, tmp_path):
        be, _, _ = _trained_logreg()
        prof = _profile_for(be)
        store = CalibrationProfileStore(tmp_path)
        store.save(prof)
        with pytest.raises(HugrGateError):
            store.save(prof)


class TestCalibratedBackend:
    def test_calibration_profile_stamped(self):
        be, states, _ = _trained_logreg()
        prof = _profile_for(be)
        wrapped = CalibratedBackend(be, prof)
        r = wrapped.evaluate(states[0], SPEC)
        assert r.calibration_profile == "toy-platt@1.0.0"
        assert abs(sum(r.distribution.values()) - 1.0) < 1e-6
        assert r.value in ("neg", "pos")

    def test_supports_delegates(self):
        be, _, _ = _trained_logreg()
        wrapped = CalibratedBackend(be, _profile_for(be))
        assert wrapped.supports(SPEC)
        assert wrapped.calibration_info()["calibrated"] is True

    def test_needs_proba_dict(self):
        class NoProba:
            name = "x"
        with pytest.raises(CalibrationError):
            CalibratedBackend(NoProba(), CalibrationProfile(name="p"))


# ---------------------------------------------------------------------------
# Slice 30: calibrated classifier milestone
# ---------------------------------------------------------------------------

class TestCalibratedMilestone:
    def test_ece_improves_end_to_end(self):
        rng = np.random.default_rng(11)
        classes = ["ignore", "log", "inspect", "escalate"]

        def gen(n, shift=False):
            sev = rng.uniform(0, 10, n)
            err = rng.beta(2, 8, n)
            risk = 0.6 * sev / 10 + 0.4 * err + rng.normal(0, 0.05, n)
            idx = np.clip(np.digitize(risk, [0.25, 0.45, 0.65]), 0, 3)
            states = [{"severity": float(sev[i]), "error_rate": float(err[i])}
                      for i in range(n)]
            labels = [classes[int(k)] for k in idx]
            if shift:  # prior shift: oversample "escalate" in training
                extra = [(dict(s), l) for s, l in zip(states, labels)
                         if l == "escalate"] * 2
                states += [s for s, _ in extra]
                labels += [l for _, l in extra]
            return states, labels

        tr_s, tr_l = gen(800, shift=True)
        va_s, va_l = gen(400)
        te_s, te_l = gen(400)

        pipe = Pipeline([NumericEncoder(["severity", "error_rate"])])
        be = LogisticRegressionBackend("ms", pipe, C=1.0)
        be.train(list(zip(tr_s, tr_l)))
        spec = DecisionSpec(type="categorical", options=classes)

        raw_va = [be.predict_proba_dict(s) for s in va_s]
        params = {}
        for cls in classes:
            scores = [d[cls] for d in raw_va]
            labs = [1 if l == cls else 0 for l in va_l]
            params[cls] = PlattCalibrator().fit(scores, labs).get_params()
        prof = CalibrationProfile(name="ms-platt", calibrator_name="platt",
                                  calibrator_params=params,
                                  backend_name=be.name, model_name="ms")
        wrapped = CalibratedBackend(be, prof)

        raw_te = [be.predict_proba_dict(s) for s in te_s]
        cal_te = [wrapped.evaluate(s, spec).distribution for s in te_s]
        ece_before = ece_multiclass(te_l, raw_te)
        ece_after = ece_multiclass(te_l, cal_te)
        assert ece_after < ece_before, \
            f"ECE did not improve: {ece_before:.4f} -> {ece_after:.4f}"
