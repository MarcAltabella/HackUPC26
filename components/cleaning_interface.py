from __future__ import annotations

from scr.dense_training_base import DenseTrainingBase, DriverVector


class CleaningInterfaceModel(DenseTrainingBase):
    def __init__(self) -> None:
        super().__init__(component_name="cleaning_interface")

    def physics_health(self, drivers: DriverVector, cross_component_factor: float) -> float:
        solvent_stress = drivers.operational_load * (0.7 + drivers.humidity_contamination)
        exp_term = self._exp_decay(solvent_stress, alpha=0.09)
        weibull_term = self._weibull_survival(solvent_stress, scale=12.0, shape=1.7)
        maintenance = 0.22 * drivers.maintenance_level
        return exp_term * weibull_term + maintenance - 0.05 * cross_component_factor

    def derive_metrics(self, health: float, drivers: DriverVector) -> dict[str, float]:
        wipe_efficiency = max(0.0, health - drivers.humidity_contamination * 0.1)
        residue_index = min(1.0, 1.0 - wipe_efficiency)
        return {
            "wipe_efficiency": float(wipe_efficiency),
            "residue_index": float(residue_index),
        }
