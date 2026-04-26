from __future__ import annotations

from scr.dense_training_base import DenseTrainingBase, DriverVector


class RecoaterBladeModel(DenseTrainingBase):
    def __init__(self) -> None:
        super().__init__(component_name="recoater_blade")

    def physics_health(self, drivers: DriverVector, cross_component_factor: float) -> float:
        abrasion = drivers.operational_load * (1.0 + 1.2 * drivers.humidity_contamination)
        stress = abrasion * (1.0 + 0.5 * cross_component_factor)
        exp_term = self._exp_decay(stress, alpha=0.11)
        weibull_term = self._weibull_survival(drivers.operational_load, scale=10.0, shape=1.8)
        maintenance = 1.0 - 0.25 * drivers.maintenance_level
        return exp_term * weibull_term * maintenance

    def derive_metrics(self, health: float, drivers: DriverVector) -> dict[str, float]:
        thickness_mm = 1.6 * health
        roughness_um = 4.5 + (1.0 - health) * 12.0 + drivers.humidity_contamination * 2.5
        return {
            "thickness_mm": float(thickness_mm),
            "roughness_um": float(roughness_um),
        }
