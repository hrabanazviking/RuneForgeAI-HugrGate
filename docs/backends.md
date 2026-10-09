# Backends

## RuleBackend (`hugrgate.backends.rules`)

Deterministic predicates and decision tables. Operators: eq, ne, gt, gte,
lt, lte, in, contains, exists. First-match wins; default rules last.
YAML-loadable. Confidence → full distribution.

## LogisticRegressionBackend (`hugrgate.backends.logreg`)

scikit-learn logistic regression. Trains on `(features, label)` pairs.
Save/load with manifest.

## RandomForestBackend (`hugrgate.backends.forest`)

Random forest classifier. Feature importances in result metadata.

## GradientBoostingBackend (`hugrgate.backends.boosting`)

Histogram gradient boosting with early stopping.

## PrototypeBackend (`hugrgate.backends.embedding`)

Embedding-based prototype classification. Cosine similarity to class
prototypes → softmax distribution. Ships with a dependency-free
hash embedding for offline use.

## NLIBackend (`hugrgate.backends.nli`)

Natural language inference: statement + premise → entailment probability.
Requires an open NLI model; graceful `BackendUnavailable` without one.

## LLMBackend (`hugrgate.backends.llm`)

Local open-weight LLM with **constrained decoding** — only spec-valid
tokens are ever emitted. Token budget, timeout, never invalid values.

## Writing Your Own

Subclass `Backend`, implement `capabilities()`, `supports()`,
`evaluate()`, `health()`. Register with `BackendRegistry` or `HugrGate.register()`.
