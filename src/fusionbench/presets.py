"""Model registry, panels, and the five v0 recipes.

Prices and the mock SKILL table below are PLACEHOLDERS for a runnable skeleton.
Replace prices with live OpenRouter numbers before any real-run cost claim.
"""
from __future__ import annotations

from .config import ModelSpec, RecipeConfig

# --- model registry (OpenRouter slugs; verify exact slugs before a real run) ---
MODELS: dict[str, ModelSpec] = {
    "google/gemini-3-flash":      ModelSpec("google/gemini-3-flash", "Gemini 3 Flash", "google", 0.15, 0.60),
    "moonshotai/kimi-k2.6":       ModelSpec("moonshotai/kimi-k2.6", "Kimi K2.6", "moonshot", 0.30, 1.20),
    "deepseek/deepseek-v4-pro":   ModelSpec("deepseek/deepseek-v4-pro", "DeepSeek V4 Pro", "deepseek", 0.27, 1.10),
    "google/gemini-3-pro":        ModelSpec("google/gemini-3-pro", "Gemini 3 Pro", "google", 1.25, 5.00),
    "openai/gpt-5.5":             ModelSpec("openai/gpt-5.5", "GPT-5.5", "openai", 2.00, 8.00),
    "anthropic/claude-fable-5":   ModelSpec("anthropic/claude-fable-5", "Claude Fable 5", "anthropic", 3.00, 15.00),
    "anthropic/claude-opus-4.8":  ModelSpec("anthropic/claude-opus-4.8", "Claude Opus 4.8", "anthropic", 2.50, 12.00),
}

CHEAP_PANEL = ("google/gemini-3-flash", "moonshotai/kimi-k2.6", "deepseek/deepseek-v4-pro")
STRONG_PANEL = ("anthropic/claude-fable-5", "openai/gpt-5.5", "google/gemini-3-pro")
BEST_SINGLE = "anthropic/claude-fable-5"

TASK_TYPES = ("code", "deep_research", "multihop_qa", "math", "factual")

# Mock-only: per-model P(correct) by task type. Illustrative — NOT real capability.
SKILL: dict[str, dict[str, float]] = {
    "anthropic/claude-fable-5":  {"code": .85, "deep_research": .60, "multihop_qa": .66, "math": .80, "factual": .88},
    "openai/gpt-5.5":            {"code": .80, "deep_research": .62, "multihop_qa": .67, "math": .78, "factual": .86},
    "google/gemini-3-pro":       {"code": .72, "deep_research": .70, "multihop_qa": .70, "math": .72, "factual": .85},
    "anthropic/claude-opus-4.8": {"code": .80, "deep_research": .63, "multihop_qa": .66, "math": .77, "factual": .86},
    "google/gemini-3-flash":     {"code": .58, "deep_research": .55, "multihop_qa": .58, "math": .55, "factual": .80},
    "moonshotai/kimi-k2.6":      {"code": .60, "deep_research": .57, "multihop_qa": .60, "math": .58, "factual": .78},
    "deepseek/deepseek-v4-pro":  {"code": .62, "deep_research": .58, "multihop_qa": .61, "math": .64, "factual": .79},
}
# Mock-only: extra P(correct) for source_pool on coverage-heavy types (it "sees" the panel's finds).
COVERAGE_BOOST: dict[str, float] = {"deep_research": .12, "multihop_qa": .10}


def build_v0_recipes(
    best: str = BEST_SINGLE,
    cheap_panel: tuple[str, ...] = CHEAP_PANEL,
    strong_panel: tuple[str, ...] = STRONG_PANEL,
    n_self_moa: int = 5,
) -> list[RecipeConfig]:
    """The five v0 arms. Judges are chosen CROSS-FAMILY to the panel (self-preference control)."""
    return [
        RecipeConfig("best-single", "best_single", single=best, topology="single"),
        RecipeConfig("self-moa", "self_moa", single=best, n_samples=n_self_moa, topology="self_moa"),
        RecipeConfig(
            "fusion-cheap", "fusion", panel=cheap_panel,
            judge="anthropic/claude-opus-4.8",   # no panel member is anthropic -> clean
            synth="anthropic/claude-opus-4.8", topology="panel_judge_synth",
        ),
        RecipeConfig(
            "fusion-strong", "fusion", panel=strong_panel,
            judge="moonshotai/kimi-k2.6",        # cross-family to anthropic/openai/google panel
            synth="anthropic/claude-opus-4.8", topology="panel_judge_synth",
        ),
        RecipeConfig("source-pool", "source_pool", panel=cheap_panel, single=best, topology="source_pool"),
    ]
