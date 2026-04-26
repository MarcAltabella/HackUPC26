from __future__ import annotations

from models.src.dense_training_base import DenseTrainingBase, DriverVector


class LinearGuideRailModel(DenseTrainingBase):
    def __init__(self) -> None:
        super().__init__(component_name="linear_guide_rail")

    def physics_health(self, drivers: DriverVector, cross_component_factor: float) -> float:
        contamination_load = drivers.operational_load * (1.0 + drivers.humidity_contamination)
        exp_term = self._exp_decay(contamination_load, alpha=0.07)
        weibull_term = self._weibull_survival(drivers.operational_load, scale=15.0, shape=2.0)
        maintenance = 1.0 - 0.18 * drivers.maintenance_level
        return exp_term * weibull_term * maintenance - 0.10 * cross_component_factor

    def derive_metrics(self, health: float, drivers: DriverVector) -> dict[str, float]:
        misalignment_mm = (1.0 - health) * 0.35 + drivers.operational_load * 0.01
        friction_coeff = 0.08 + (1.0 - health) * 0.16
        return {
            "misalignment_mm": float(misalignment_mm),
            "friction_coeff": float(friction_coeff),
        }
