"""Metric and slice registry: the single source of truth for dimensions."""

from __future__ import annotations

from typing import Iterable

from reproduce.eval.registry.spec import LAYERS, MetricSpec, SliceSpec


class MetricRegistry:
    def __init__(self) -> None:
        self._metrics: dict[str, MetricSpec] = {}
        self._slices: dict[str, SliceSpec] = {}

    # -- registration -------------------------------------------------
    def register(self, spec: MetricSpec) -> MetricSpec:
        if spec.id in self._metrics:
            raise ValueError(f"duplicate metric id: {spec.id}")
        self._metrics[spec.id] = spec
        return spec

    def register_all(self, specs: Iterable[MetricSpec]) -> None:
        for spec in specs:
            self.register(spec)

    def register_slice(self, spec: SliceSpec) -> SliceSpec:
        if spec.id in self._slices:
            raise ValueError(f"duplicate slice id: {spec.id}")
        self._slices[spec.id] = spec
        return spec

    # -- lookup --------------------------------------------------------
    def get(self, metric_id: str) -> MetricSpec:
        return self._metrics[metric_id]

    def metrics(self, *, layer: str | None = None, publication: str | None = None) -> list[MetricSpec]:
        result = list(self._metrics.values())
        if layer is not None:
            result = [spec for spec in result if spec.layer == layer]
        if publication is not None:
            result = [spec for spec in result if spec.publication == publication]
        return result

    def engine_metrics(self) -> list[MetricSpec]:
        return [spec for spec in self._metrics.values() if spec.engine_computed]

    def slices(self) -> list[SliceSpec]:
        return list(self._slices.values())

    def get_slice(self, slice_id: str) -> SliceSpec:
        return self._slices[slice_id]

    # -- validation ----------------------------------------------------
    def validate(self) -> None:
        """Cross-spec invariants; individual specs validate on construction."""
        for layer in LAYERS:
            _ = layer  # layers are fixed; per-spec checks happen in MetricSpec
        slice_fields = {spec.field for spec in self._slices.values()}
        for spec in self._slices.values():
            if not spec.id or not spec.field:
                raise ValueError(f"slice {spec.id!r} needs id and field")
        if len(slice_fields) != len(set(slice_fields)):
            raise ValueError("slice fields must be unique")


_DEFAULT: MetricRegistry | None = None


def default_registry() -> MetricRegistry:
    """Registry with all builtin layers registered (memoized)."""
    global _DEFAULT
    if _DEFAULT is None:
        from reproduce.eval.registry.builtin import register_builtins

        registry = MetricRegistry()
        register_builtins(registry)
        registry.validate()
        _DEFAULT = registry
    return _DEFAULT
