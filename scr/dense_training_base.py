from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import torch
from torch import nn


class OperationalStatus(StrEnum):
    FUNCTIONAL = "FUNCTIONAL"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    FAILED = "FAILED"


@dataclass(frozen=True)
class DriverVector:
    """Input contract for environmental and operational drivers."""

    temperature_stress: float
    humidity_contamination: float
    operational_load: float
    maintenance_level: float


@dataclass(frozen=True)
class ComponentReport:
    """Output contract for each component telemetry report."""

    component: str
    health_index: float
    operational_status: OperationalStatus
    metrics: dict[str, float]


@dataclass(frozen=True)
class OptimizerConfig:
    lr: float = 1e-3
    weight_decay: float = 1e-4


class DenseTrainingBase(nn.Module):
    """
    Shared architecture for all HP S100 component models.

    It mixes deterministic physics-inspired degradation with a small dense
    correction head so all components share the same optimization/training
    interface when data-driven fine-tuning is needed.
    """

    def __init__(self, component_name: str, hidden_dim: int = 32, dropout: float = 0.1):
        super().__init__()
        self.component_name = component_name

        # Shared neural correction block: [temp, humidity, load, maintenance].
        self.correction_net = nn.Sequential(
            nn.Linear(4, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1),
            nn.Tanh(),
        )
        self._init_weights()

    def _init_weights(self) -> None:
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.kaiming_uniform_(module.weight, nonlinearity="relu")
                nn.init.zeros_(module.bias)

    @staticmethod
    def build_optimizer(model: nn.Module, cfg: OptimizerConfig) -> torch.optim.Optimizer:
        return torch.optim.AdamW(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)

    @staticmethod
    def _clamp01(value: float) -> float:
        return float(max(0.0, min(1.0, value)))

    @staticmethod
    def _status_from_health(health: float) -> OperationalStatus:
        if health <= 0.15:
            return OperationalStatus.FAILED
        if health <= 0.35:
            return OperationalStatus.CRITICAL
        if health <= 0.70:
            return OperationalStatus.DEGRADED
        return OperationalStatus.FUNCTIONAL

    @staticmethod
    def _exp_decay(stress: float, alpha: float) -> float:
        return float(torch.exp(torch.tensor(-alpha * max(stress, 0.0))).item())

    @staticmethod
    def _weibull_survival(load: float, scale: float, shape: float) -> float:
        x = max(load, 0.0) / max(scale, 1e-6)
        return float(torch.exp(torch.tensor(-(x**shape))).item())

    def _forward_correction(self, drivers: DriverVector) -> float:
        x = torch.tensor(
            [
                drivers.temperature_stress,
                drivers.humidity_contamination,
                drivers.operational_load,
                drivers.maintenance_level,
            ],
            dtype=torch.float32,
        )
        return float(self.correction_net(x).item())

    def physics_health(self, drivers: DriverVector, cross_component_factor: float) -> float:
        """Override in child classes with component-specific degradation logic."""
        raise NotImplementedError

    def derive_metrics(self, health: float, drivers: DriverVector) -> dict[str, float]:
        """Override in child classes with component-specific telemetry metrics."""
        raise NotImplementedError

    def forward(self, drivers: DriverVector, cross_component_factor: float = 0.0) -> ComponentReport:
        base = self.physics_health(drivers, cross_component_factor)

        # Keep deterministic defaults by not using learned correction in inference.
        correction = 0.0
        health = self._clamp01(base + correction)

        return ComponentReport(
            component=self.component_name,
            health_index=health,
            operational_status=self._status_from_health(health),
            metrics=self.derive_metrics(health, drivers),
        )


__all__ = [
    "ComponentReport",
    "DenseTrainingBase",
    "DriverVector",
    "OperationalStatus",
    "OptimizerConfig",
]
