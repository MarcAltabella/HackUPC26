from __future__ import annotations

from dataclasses import dataclass, field

from models.src.dense_training_base import ComponentReport, DriverVector

from models.components.cleaning_interface import CleaningInterfaceModel
from models.components.heating_elements import HeatingElementsModel
from models.components.insulation_panels import InsulationPanelsModel
from models.components.linear_guide_rail import LinearGuideRailModel
from models.components.nozzle_plate import NozzlePlateModel
from models.components.recoater_blade import RecoaterBladeModel
from models.components.recoater_drive_motor import RecoaterDriveMotorModel
from models.components.temperature_sensors import TemperatureSensorsModel
from models.components.thermal_firing_resistors import ThermalFiringResistorsModel


@dataclass
class HP100Engine:
    """Deterministic logic engine for all HP Metal Jet S100 components."""

    recoater_blade: RecoaterBladeModel = field(default_factory=RecoaterBladeModel)
    recoater_drive_motor: RecoaterDriveMotorModel = field(
        default_factory=RecoaterDriveMotorModel
    )
    linear_guide_rail: LinearGuideRailModel = field(default_factory=LinearGuideRailModel)
    nozzle_plate: NozzlePlateModel = field(default_factory=NozzlePlateModel)
    thermal_firing_resistors: ThermalFiringResistorsModel = field(
        default_factory=ThermalFiringResistorsModel
    )
    cleaning_interface: CleaningInterfaceModel = field(
        default_factory=CleaningInterfaceModel
    )
    heating_elements: HeatingElementsModel = field(default_factory=HeatingElementsModel)
    temperature_sensors: TemperatureSensorsModel = field(
        default_factory=TemperatureSensorsModel
    )
    insulation_panels: InsulationPanelsModel = field(default_factory=InsulationPanelsModel)

    def step(self, drivers: DriverVector) -> dict[str, ComponentReport]:
        reports: dict[str, ComponentReport] = {}

        rb = self.recoater_blade(drivers)
        reports[rb.component] = rb

        # Cascading contamination effect: blade wear hurts printhead health.
        contamination_feedback = 1.0 - rb.health_index
        np = self.nozzle_plate(drivers, cross_component_factor=contamination_feedback)
        reports[np.component] = np

        ci = self.cleaning_interface(drivers, cross_component_factor=contamination_feedback)
        reports[ci.component] = ci

        # Thermal feedback: insulation and sensors influence heating load.
        ip = self.insulation_panels(drivers)
        ts = self.temperature_sensors(drivers)
        thermal_feedback = ((1.0 - ip.health_index) + (1.0 - ts.health_index)) / 2.0

        he = self.heating_elements(drivers, cross_component_factor=thermal_feedback)
        reports[ip.component] = ip
        reports[ts.component] = ts
        reports[he.component] = he

        rdm = self.recoater_drive_motor(drivers, cross_component_factor=contamination_feedback)
        lgr = self.linear_guide_rail(drivers, cross_component_factor=contamination_feedback)
        tfr = self.thermal_firing_resistors(drivers, cross_component_factor=thermal_feedback)

        reports[rdm.component] = rdm
        reports[lgr.component] = lgr
        reports[tfr.component] = tfr

        return reports
