"""The router — pick an `EngineConfig` for (model, target, budget).

v0.3 is a TRANSPARENT HEURISTIC, not a learned/optimized policy: a short ordered
list of (hardware, preference) -> (method, scheme) rules, each carrying the
human-readable WHY it fired. The router only ever returns a config that an engine
reported feasible for the target — it never fabricates one. If the preferred
rule's config is not in the feasible set it falls through to the next rule; if
nothing is feasible it raises. Every rationale string is tagged so the heuristic
nature is legible at the call site.
"""

from __future__ import annotations

from quantfit.engines.base import Budget, Engine, EngineConfig, Plan, Target

# Every rationale carries this tag so callers see the decision is a v0.3 heuristic.
HEURISTIC_TAG = "v0.3 transparent heuristic"

# Routing-rule targets: the (method, scheme) each rule selects. These must match
# what the engines' feasible() reports; the router resolves against that set only.
METHOD_GGUF, SCHEME_GGUF = "gguf", "Q4_K_M"
METHOD_FP8, SCHEME_FP8 = "fp8", "FP8_DYNAMIC"
METHOD_GPTQ, SCHEME_GPTQ = "gptq", "W4A16"
METHOD_AWQ, SCHEME_AWQ = "awq", "W4A16_ASYM"

# Target/budget vocabulary the rule guards switch on (mirrors the base contract).
DEVICE_CPU, DEVICE_CUDA = "cpu", "cuda"
SERVE_LLAMACPP = "llama.cpp"
PREFER_SPEED, PREFER_SIZE = "speed", "size"
FP8_ARCHS = ("hopper", "blackwell")  # archs with first-class FP8 tensor cores


def _gather_feasible(target: Target, engines: list[Engine]) -> list[EngineConfig]:
    """Union of every engine's feasible configs for this target."""
    feasible: list[EngineConfig] = []
    for engine in engines:
        feasible.extend(engine.feasible(target))
    return feasible


def _find(feasible: list[EngineConfig], method: str, scheme: str) -> EngineConfig | None:
    """Return the feasible config matching (method, scheme), or None if absent."""
    for config in feasible:
        if config.method == method and config.scheme == scheme:
            return config
    return None


def _candidate_rules(target: Target, budget: Budget) -> list[tuple[str, str, str]]:
    """Ordered (method, scheme, rationale) for rules whose guard fires, top priority first."""
    rules: list[tuple[str, str, str]] = []

    # 1. CPU / llama.cpp serving -> GGUF k-quant (the only path that runs there).
    if target.serve == SERVE_LLAMACPP or target.device == DEVICE_CPU:
        rules.append((METHOD_GGUF, SCHEME_GGUF, f"{HEURISTIC_TAG}: CPU/llama.cpp serving target -> GGUF Q4_K_M"))

    # 2. Speed on an FP8-native GPU -> FP8 dynamic (no calib, ~FP16 quality).
    if budget.prefer == PREFER_SPEED and target.gpu_arch in FP8_ARCHS:
        rules.append(
            (
                METHOD_FP8,
                SCHEME_FP8,
                f"{HEURISTIC_TAG}: FP8-capable GPU + speed preference -> FP8 dynamic, ~FP16 quality",
            )
        )

    # 3. Size preference -> 4-bit GPTQ (smallest weight-only footprint here).
    if budget.prefer == PREFER_SIZE:
        rules.append((METHOD_GPTQ, SCHEME_GPTQ, f"{HEURISTIC_TAG}: size preference -> 4-bit GPTQ"))

    # 4. Default GPU path -> AWQ 4-bit (best 4-bit quality for instruct models).
    if target.device == DEVICE_CUDA:
        rules.append(
            (
                METHOD_AWQ,
                SCHEME_AWQ,
                f"{HEURISTIC_TAG}: default GPU path -> AWQ 4-bit, best quality for instruct models",
            )
        )

    return rules


def route(model_id: str, target: Target, budget: Budget, engines: list[Engine]) -> Plan:
    """Route (model, target, budget) to a feasible `EngineConfig` with a legible rationale."""
    feasible = _gather_feasible(target, engines)
    if not feasible:
        raise ValueError(
            f"no engine reports a feasible config for {model_id} on target "
            f"{target.device}/{target.gpu_arch or 'no-gpu'}; cannot route."
        )

    for method, scheme, rationale in _candidate_rules(target, budget):
        config = _find(feasible, method, scheme)
        if config is not None:
            return Plan(config=config, rationale=rationale)

    # Guards fired but none of their configs were feasible (or no guard fired at all).
    offered = [(c.method, c.scheme) for c in feasible]
    raise ValueError(
        f"no routing rule matched a feasible config for {model_id} on "
        f"{target.device}/{target.gpu_arch or 'no-gpu'} (prefer={budget.prefer}); "
        f"feasible set was {offered}."
    )
