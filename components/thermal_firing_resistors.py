from __future__ import annotations

from scr.dense_training_base import DenseTrainingBase, DriverVector


class ThermalFiringResistorsModel(DenseTrainingBase):
    def __init__(self) -> None:
        super().__init__(component_name="thermal_firing_resistors")

    def physics_health(self, drivers: DriverVector, cross_component_factor: float) -> float:
        thermal_cycles = drivers.operational_load * (1.0 + drivers.temperature_stress * 1.1)
        exp_term = self._exp_decay(thermal_cycles, alpha=0.10)
        weibull_term = self._weibull_survival(thermal_cycles, scale=11.5, shape=1.9)
        maintenance = 1.0 - 0.12 * drivers.maintenance_level
        return exp_term * weibull_term * maintenance - 0.08 * cross_component_factor

    def derive_metrics(self, health: float, drivers: DriverVector) -> dict[str, float]:
        ohm_drift_pct = (1.0 - health) * 35.0 + drivers.temperature_stress * 3.0
        firing_latency_ms = 0.15 + (1.0 - health) * 0.6
        return {
            "resistance_drift_pct": float(ohm_drift_pct),
            "firing_latency_ms": float(firing_latency_ms),
        }
