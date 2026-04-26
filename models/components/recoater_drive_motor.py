from __future__ import annotations

from models.src.dense_training_base import DenseTrainingBase, DriverVector


class RecoaterDriveMotorModel(DenseTrainingBase):
    def __init__(self) -> None:
        super().__init__(component_name="recoater_drive_motor")

    def physics_health(self, drivers: DriverVector, cross_component_factor: float) -> float:
        fatigue = drivers.operational_load * (1.0 + drivers.temperature_stress * 0.5)
        exp_term = self._exp_decay(fatigue, alpha=0.08)
        weibull_term = self._weibull_survival(fatigue, scale=13.0, shape=2.1)
        maintenance_boost = 0.20 * drivers.maintenance_level
        return (exp_term * weibull_term) + maintenance_boost - 0.12 * cross_component_factor

    def derive_metrics(self, health: float, drivers: DriverVector) -> dict[str, float]:
        stall_probability = min(1.0, (1.0 - health) * 0.9 + drivers.operational_load * 0.03)
        torque_margin = 1.0 - stall_probability
        return {
            "stall_probability": float(stall_probability),
            "torque_margin": float(max(0.0, torque_margin)),
        }
