export type Severity = "INFO" | "WARNING" | "CRITICAL";
export type ComponentStatus = "FUNCTIONAL" | "DEGRADED" | "CRITICAL" | "FAILED";
export type ActionLabel = "do_nothing" | "light_service" | "full_maintenance";

export interface Citation {
  run_id: string;
  run_number: number;
  t: number;
  field: string;
  value?: number | string | boolean | null;
}

export interface ComponentPrediction {
  label: number;
  status: ComponentStatus;
  confidence: number;
  probabilities: Record<ComponentStatus, number>;
}

export interface ComponentState extends ComponentPrediction {
  health: number;
}

export interface BladeState extends ComponentState {
  thickness_mm: number;
}

export interface MotorState extends ComponentState {
  vibration_mm_s: number;
}

export interface RailState extends ComponentState {
  deviation_um: number;
}

export interface NozzleState extends ComponentState {
  clog_probability: number;
}

export interface ResistorState extends ComponentState {
  drift_pct: number;
}

export interface CleaningState extends ComponentState {
  efficiency: number;
}

export interface HeaterState extends ComponentState {
  resistance_ohm: number;
}

export interface SensorState extends ComponentState {
  measurement_error_c: number;
}

export interface InsulationState extends ComponentState {
  thermal_resistance: number;
}

export interface EnvironmentalDrivers {
  temperature: number;
  humidity: number;
  load: number;
  maintenance_level: number;
  is_shock: boolean;
  steps_since_maintenance: number;
  cumulative_shocks: number;
}

export interface MaintenanceRecommendation {
  action: 0 | 1 | 2;
  action_label: ActionLabel;
  maintenance_level: number;
  reward: number;
}

export interface DiagnosticAlert {
  id: string;
  severity: "WARNING" | "CRITICAL";
  subsystem: string;
  component: string;
  component_key: string;
  metric: string;
  summary: string;
  reasoning: string[];
  actions: string[];
  query: string;
  citations: Citation[];
}

export interface MachineState {
  scenario_id: string;
  run_number: number;
  t: number;
  drivers: EnvironmentalDrivers;
  recoating: {
    subsystem_health: number;
    blade: BladeState;
    motor: MotorState;
    rail: RailState;
  };
  printhead: {
    subsystem_health: number;
    nozzle: NozzleState;
    resistor: ResistorState;
    cleaning: CleaningState;
  };
  thermal: {
    subsystem_health: number;
    heater: HeaterState;
    sensor: SensorState;
    insulation: InsulationState;
  };
  model_predictions: Record<string, ComponentPrediction>;
  maintenance_recommendation: MaintenanceRecommendation;
  alerts: DiagnosticAlert[];
}

export interface HistoryRow {
  scenario_id?: string;
  t: number;
  temperature: number;
  humidity: number;
  health_recoating: number;
  health_printhead: number;
  health_thermal: number;
  status_blade: string;
  status_nozzle: string;
  status_heater: string;
  health_blade?: number;
  health_motor?: number;
  health_rail?: number;
  health_nozzle?: number;
  health_resistor?: number;
  health_cleaning?: number;
  health_heater?: number;
  health_sensor?: number;
  health_insulation?: number;
}

export interface ScenarioMeta {
  scenario_id: string;
  env_profile: string;
  maintenance_schedule: string;
  run_number: number;
  min_t: number;
  max_t: number;
  tick_count: number;
}

export interface ChatResponse {
  severity: Severity;
  summary: string;
  answer: string;
  reasoning_summary: string[];
  citations: Citation[];
  recommended_actions: string[];
}
