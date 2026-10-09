# HugrGate benchmark datasets

Three **original** datasets built for HugrGate (Slice 46). Every template was
written for this project — nothing was copied from existing benchmarks.

| Dataset | Task | Spec type | Classes / levels | Items | Balance |
|---|---|---|---|---|---|
| `intent_500.json` | support-ticket intent | categorical | billing, technical, account, refund, shipping | 500 | 100 each |
| `urgency_500.json` | event urgency | ordinal | low, medium, high, critical | 500 | 125 each |
| `triage_500.json` | security-event triage | categorical | ignore, log, investigate, escalate | 500 | 125 each |

## Item schema

```json
{
  "id": "intent-0001",
  "state": {"ticket": "I was charged $12.99 twice...", "channel": "email"},
  "spec_type": "categorical",
  "expected": "billing"
}
```

Each file is a single JSON object:

```json
{
  "name": "intent_500",
  "version": "1.0.0",
  "seed": 20261009,
  "spec": {"type": "categorical", "options": [...]},
  "items": [...]
}
```

## Reproducing

```bash
python benchmarks/build.py --out benchmarks
```

Generation is fully deterministic (seeded PRNG, seed `20261009`): rebuilding
produces byte-identical files. Verify integrity with:

```bash
cd benchmarks && sha256sum -c CHECKSUMS.sha256
```

## Design notes

- Templates embed class-indicative keywords at natural rates, so a
  keyword-overlap baseline scores meaningfully above chance while a
  uniform baseline sits at chance — the harness measures the gap.
- `state` carries realistic side-channel fields (`channel`, `source`,
  `asset`) that backends may use or ignore.
- The ordinal `urgency_500` levels are ordered low → critical; ordinal-aware
  backends can exploit the ordering, categorical ones treat them as labels.

## Running the harness

```bash
hugrgate bench --dataset benchmarks/triage_500.json \
    --backends keyword,uniform --out /tmp/bench.json
hugrgate report --report /tmp/bench.json --out /tmp/bench.md
```
