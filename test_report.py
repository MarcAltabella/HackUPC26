import sys
sys.path.append("/home/swallow/Desktop/Projects/HackUPC2026")
from models.components.hp_s100_engine import HP100Engine
from models.src.dense_training_base import DriverVector

engine = HP100Engine()
drivers = DriverVector(temperature_stress=0.5, humidity_contamination=0.4, operational_load=0.8, maintenance_level=0.0)
reports = engine.step(drivers)
for k, v in reports.items():
    print(k)
    print("Health:", v.health_index)
    print("Metrics:", v.metrics)
