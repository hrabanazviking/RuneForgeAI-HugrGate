"""Edge Intelligence runtime — Campaign VIII (slices 176-200).

A local-first HugrGate extension for ARM64 edge devices (Raspberry Pi,
NVIDIA Jetson, Hailo accelerators, OpenVINO NPUs): platform detection,
resource-aware operating modes, quantized inference, NPU adapter
boundaries, edge-tuned storage/cache/telemetry, benchmarking, fault
injection, and a release gate.

No edge hardware is present in this build environment: every sensor,
accelerator, and board profile is a *testable abstraction* backed by an
injectable mock. Anything that can only be proven on real silicon is
marked ``NEEDS_HARDWARE_VALIDATION`` at the call site and collected in
``hugrgate/edge/NEEDS_HARDWARE_VALIDATION.md``-style notes inside each
slice doc (Execution Law, rule 13).
"""

from __future__ import annotations

__all__: list[str] = []
