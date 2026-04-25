from __future__ import annotations

from scr.dense_training_base import DenseTrainingBase, DriverVector


class InsulationPanelsModel(DenseTrainingBase):
    def __init__(self) -> None:
        super().__init__(component_name="insulation_panels")

    def physics_health(self, drivers: DriverVector, cross_component_factor: float) -> float:
        aging_stress = drivers.operational_load * (0.6 + drivers.humidity_contamination)
        exp_term = self._exp_decay(aging_stress, alpha=0.05)
        weibull_term = self._weibull_survival(aging_stress, scale=20.0, shape=1.5)
        maintenance = 1.0 - 0.10 * drivers.maintenance_level
        return exp_term * weibull_term * maintenance - 0.10 * cross_component_factor

    def derive_metrics(self, health: float, drivers: DriverVector) -> dict[str, float]:
        heat_loss_factor = min(1.0, (1.0 - health) * 0.8 + drivers.humidity_contamination * 0.2)
        retention_efficiency = max(0.0, 1.0 - heat_loss_factor)
        return {
            "heat_loss_factor": float(heat_loss_factor),
            "retention_efficiency": float(retention_efficiency),
        }
