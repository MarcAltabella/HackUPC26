from __future__ import annotations

from scr.dense_training_base import DenseTrainingBase, DriverVector


class TemperatureSensorsModel(DenseTrainingBase):
    def __init__(self) -> None:
        super().__init__(component_name="temperature_sensors")

    def physics_health(self, drivers: DriverVector, cross_component_factor: float) -> float:
        drift_stress = drivers.operational_load * (0.9 + drivers.temperature_stress)
        exp_term = self._exp_decay(drift_stress, alpha=0.06)
        weibull_term = self._weibull_survival(drift_stress, scale=18.0, shape=1.6)
        maintenance = 0.15 * drivers.maintenance_level
        return exp_term * weibull_term + maintenance - 0.06 * cross_component_factor

    def derive_metrics(self, health: float, drivers: DriverVector) -> dict[str, float]:
        sensor_drift_c = (1.0 - health) * 6.0 + drivers.temperature_stress * 0.5
        confidence = max(0.0, 1.0 - sensor_drift_c / 8.0)
        return {
            "sensor_drift_c": float(sensor_drift_c),
            "measurement_confidence": float(confidence),
        }
