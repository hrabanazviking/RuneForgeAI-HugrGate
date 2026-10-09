"""Calibrated triage milestone. Slice 30.

End-to-end demonstration of trustworthy ML decisions:

1. Generate synthetic security-event data with a *prior shift* between the
   training set (over-represents "escalate") and deployment — the classic
   way production models become miscalibrated.
2. Train a :class:`LogisticRegressionBackend` on the shifted data.
3. Measure multiclass ECE of the raw model on a held-out validation set.
4. Fit per-class Platt calibrators on that validation set, store a
   :class:`CalibrationProfile`, and wrap the backend in
   :class:`CalibratedBackend`.
5. Show ECE dropping on a fresh test set, then route live decisions through
   :class:`HugrGate` with a confidence threshold policy.

Run:  ``venv/bin/python examples/calibrated_triage.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hugrgate.backends.logreg import LogisticRegressionBackend
from hugrgate.calibration import PlattCalibrator
from hugrgate.calibration.metrics import ece_multiclass
from hugrgate.calibration.profiles import (
    CalibratedBackend,
    CalibrationProfile,
    CalibrationProfileStore,
    hash_dataset,
)
from hugrgate.core import HugrGate
from hugrgate.features import (
    CategoricalEncoder,
    NumericEncoder,
    Pipeline,
)
from hugrgate.policy import DecisionPolicy
from hugrgate.spec import DecisionSpec

CLASSES = ["ignore", "log", "inspect", "escalate"]
SOURCES = ["sensor", "user", "partner"]


def generate_events(n: int, rng: np.random.Generator,
                    escalate_oversample: float = 1.0):
    """Synthetic triage events: (states, labels)."""
    severity = rng.uniform(0, 10, n)
    error_rate = rng.beta(2, 8, n)
    user_reports = rng.poisson(2.5, n).astype(float)
    source_reliability = rng.uniform(0.2, 1.0, n)
    hour = rng.integers(0, 24, n).astype(float)
    source = rng.choice(SOURCES, n, p=[0.5, 0.3, 0.2])

    risk = (0.38 * severity / 10.0
            + 0.30 * error_rate
            + 0.20 * np.minimum(user_reports, 10.0) / 10.0
            + 0.12 * (1.0 - source_reliability)
            + rng.normal(0, 0.06, n))
    idx = np.clip(np.digitize(risk, [0.22, 0.42, 0.62]), 0, 3)

    states = [
        {"severity": float(severity[i]),
         "error_rate": float(error_rate[i]),
         "user_reports": float(user_reports[i]),
         "source_reliability": float(source_reliability[i]),
         "hour": float(hour[i]),
         "source": str(source[i])}
        for i in range(n)
    ]
    labels = [CLASSES[int(k)] for k in idx]

    if escalate_oversample != 1.0:
        # Prior shift: duplicate escalate events to simulate a training set
        # collected during an incident-heavy period.
        extra_states, extra_labels = [], []
        for s, lab in zip(states, labels):
            if lab == "escalate":
                for _ in range(int(escalate_oversample) - 1):
                    extra_states.append(dict(s))
                    extra_labels.append(lab)
        states += extra_states
        labels += extra_labels
    return states, labels


def main() -> int:
    rng = np.random.default_rng(7)
    print("== HugrGate calibrated triage milestone (slice 30) ==\n")

    # Fresh demo state on every run (the store itself rejects overwrites).
    import shutil
    shutil.rmtree(".hugrgate-demo", ignore_errors=True)

    # 1. Data with prior shift: train heavy on "escalate", deploy natural.
    train_states, train_labels = generate_events(
        1200, rng, escalate_oversample=3.0)
    val_states, val_labels = generate_events(600, rng)
    test_states, test_labels = generate_events(600, rng)
    print(f"train={len(train_states)} (prior-shifted)  "
          f"val={len(val_states)}  test={len(test_states)}")

    # 2. Train the raw model.
    pipeline = Pipeline([
        NumericEncoder(["severity", "error_rate", "user_reports",
                        "source_reliability", "hour"]),
        CategoricalEncoder("source"),
    ])
    backend = LogisticRegressionBackend("triage-logreg", pipeline,
                                        version="1.0.0", C=1.0)
    metrics = backend.train(list(zip(train_states, train_labels)))
    print(f"trained: train_accuracy={metrics['train_accuracy']:.3f} "
          f"features={int(metrics['n_features'])}")

    spec = DecisionSpec(type="categorical", options=CLASSES)

    # 3. Raw ECE on validation.
    raw_val = [backend.predict_proba_dict(s) for s in val_states]
    ece_raw = ece_multiclass(val_labels, raw_val)
    print(f"\nraw model ECE (val):        {ece_raw:.4f}")

    # 4. Fit one Platt calibrator per class (one-vs-rest) on validation.
    per_class_params = {}
    per_class_scores, per_class_labels = [], []
    for cls in CLASSES:
        scores = [d[cls] for d in raw_val]
        labels = [1 if lab == cls else 0 for lab in val_labels]
        cal = PlattCalibrator().fit(scores, labels)
        per_class_params[cls] = cal.get_params()
        per_class_scores.extend(scores)
        per_class_labels.extend(labels)
    profile = CalibrationProfile(
        name="triage-platt",
        version="1.0.0",
        backend_name=backend.name,
        model_name="triage-logreg",
        model_version="1.0.0",
        calibrator_name="platt",
        calibrator_params=per_class_params,
        metrics={"ece_val_raw": ece_raw},
        dataset_hash=hash_dataset(per_class_scores, per_class_labels),
        n_samples=len(val_states),
        notes="one-vs-rest Platt on prior-shifted validation set",
    )
    store = CalibrationProfileStore(".hugrgate-demo/profiles")
    store.save(profile)
    calibrated = CalibratedBackend(backend, store.get("triage-platt"))

    # 5. ECE before/after on the untouched test set.
    raw_test = [backend.predict_proba_dict(s) for s in test_states]
    cal_test = [dict(r.distribution)
                for r in (calibrated.evaluate(s, spec) for s in test_states)]
    ece_before = ece_multiclass(test_labels, raw_test)
    ece_after = ece_multiclass(test_labels, cal_test)
    print(f"raw model ECE (test):       {ece_before:.4f}")
    print(f"calibrated ECE (test):      {ece_after:.4f}")
    improvement = (ece_before - ece_after) / max(ece_before, 1e-12) * 100
    print(f"relative ECE improvement:   {improvement:.1f}%")
    assert ece_after < ece_before, "calibration did not improve ECE"

    # 6. Live decisions through the gate with a confidence threshold.
    gate = HugrGate()
    gate.register(calibrated)
    policy = DecisionPolicy(minimum_probability=0.55)
    print("\nlive decisions (threshold 0.55):")
    demo = [
        {"severity": 9.2, "error_rate": 0.85, "user_reports": 14,
         "source_reliability": 0.9, "hour": 3, "source": "sensor"},
        {"severity": 1.1, "error_rate": 0.02, "user_reports": 0,
         "source_reliability": 0.4, "hour": 14, "source": "user"},
        {"severity": 5.0, "error_rate": 0.3, "user_reports": 3,
         "source_reliability": 0.7, "hour": 22, "source": "partner"},
    ]
    from hugrgate.errors import Abstention

    for state in demo:
        try:
            r = gate.decide(state, spec, policy)
            print(f"  -> {r.value:<8} p={r.probability:.3f} "
                  f"accepted={r.accepted} profile={r.calibration_profile} "
                  f"({r.latency_ms:.1f} ms)")
        except Abstention as e:
            print(f"  -> ABSTAIN   ({e}) — confidence below policy threshold")

    print("\nOK: calibration improved ECE and the gate decides in milliseconds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
