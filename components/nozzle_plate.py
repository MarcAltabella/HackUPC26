from __future__ import annotations

from scr.dense_training_base import DenseTrainingBase, DriverVector


class NozzlePlateModel(DenseTrainingBase):
    def __init__(self) -> None:
        super().__init__(component_name="nozzle_plate")

    def physics_health(self, drivers: DriverVector, cross_component_factor: float) -> float:
        thermal_window_penalty = abs(drivers.temperature_stress - 0.5) * 1.6
        clogging_driver = drivers.humidity_contamination + 0.6 * thermal_window_penalty
        stress = drivers.operational_load * (1.0 + clogging_driver + 0.6 * cross_component_factor)
        exp_term = self._exp_decay(stress, alpha=0.12)
        weibull_term = self._weibull_survival(drivers.operational_load, scale=9.0, shape=2.2)
        maintenance = 0.18 * drivers.maintenance_level
        return exp_term * weibull_term + maintenance

    def derive_metrics(self, health: float, drivers: DriverVector) -> dict[str, float]:
        clog_ratio = min(1.0, (1.0 - health) * 0.95 + drivers.humidity_contamination * 0.2)
        jetting_accuracy = max(0.0, 1.0 - clog_ratio)
        return {
            "clog_ratio": float(clog_ratio),
            "jetting_accuracy": float(jetting_accuracy),
        }
