from __future__ import annotations

from scr.dense_training_base import DenseTrainingBase, DriverVector


class HeatingElementsModel(DenseTrainingBase):
    def __init__(self) -> None:
        super().__init__(component_name="heating_elements")

    def physics_health(self, drivers: DriverVector, cross_component_factor: float) -> float:
        electrical_stress = drivers.operational_load * (1.0 + 1.1 * drivers.temperature_stress)
        exp_term = self._exp_decay(electrical_stress, alpha=0.10)
        weibull_term = self._weibull_survival(electrical_stress, scale=10.5, shape=2.0)
        maintenance = 1.0 - 0.16 * drivers.maintenance_level
        return exp_term * weibull_term * maintenance - 0.15 * cross_component_factor

    def derive_metrics(self, health: float, drivers: DriverVector) -> dict[str, float]:
        energy_overhead_pct = (1.0 - health) * 50.0 + drivers.temperature_stress * 4.0
        thermal_stability = max(0.0, health - drivers.temperature_stress * 0.15)
        return {
            "energy_overhead_pct": float(energy_overhead_pct),
            "thermal_stability": float(thermal_stability),
        }
