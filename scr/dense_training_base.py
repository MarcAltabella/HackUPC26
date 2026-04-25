from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import torch
from torch import Tensor, nn
from torch.utils.data import DataLoader


class OperationalStatus(StrEnum):
    FUNCTIONAL = "FUNCTIONAL"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    FAILED = "FAILED"


@dataclass(frozen=True)
class DriverVector:
    """Input contract for environmental and operational drivers."""

    temperature_stress: float
    humidity_contamination: float
    operational_load: float
    maintenance_level: float


@dataclass(frozen=True)
class ComponentReport:
    """Output contract for each component telemetry report."""

    component: str
    health_index: float
    operational_status: OperationalStatus
    metrics: dict[str, float]


@dataclass(frozen=True)
class OptimizerConfig:
    lr: float = 1e-3
    weight_decay: float = 1e-4


class DenseTrainingBase(nn.Module):
    """
    Shared architecture for all HP S100 component models.

    It mixes deterministic physics-inspired degradation with a small dense
    correction head so all components share the same optimization/training
    interface when data-driven fine-tuning is needed.
    """

    def __init__(self, component_name: str, hidden_dim: int = 32, dropout: float = 0.1):
        super().__init__()
        self.component_name = component_name

        # Shared neural correction block: [temp, humidity, load, maintenance].
        self.correction_net = nn.Sequential(
            nn.Linear(4, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1),
            nn.Tanh(),
        )
        self._init_weights()

    def _init_weights(self) -> None:
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.kaiming_uniform_(module.weight, nonlinearity="relu")
                nn.init.zeros_(module.bias)

    @staticmethod
    def build_optimizer(model: nn.Module, cfg: OptimizerConfig) -> torch.optim.Optimizer:
        return torch.optim.AdamW(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)

    @staticmethod
    def _clamp01(value: float) -> float:
        return float(max(0.0, min(1.0, value)))

    @staticmethod
    def _status_from_health(health: float) -> OperationalStatus:
        if health <= 0.15:
            return OperationalStatus.FAILED
        if health <= 0.35:
            return OperationalStatus.CRITICAL
        if health <= 0.70:
            return OperationalStatus.DEGRADED
        return OperationalStatus.FUNCTIONAL

    @staticmethod
    def _exp_decay(stress: float, alpha: float) -> float:
        return float(torch.exp(torch.tensor(-alpha * max(stress, 0.0))).item())

    @staticmethod
    def _weibull_survival(load: float, scale: float, shape: float) -> float:
        x = max(load, 0.0) / max(scale, 1e-6)
        return float(torch.exp(torch.tensor(-(x**shape))).item())

    def _forward_correction(self, drivers: DriverVector) -> float:
        x = torch.tensor(
            [
                drivers.temperature_stress,
                drivers.humidity_contamination,
                drivers.operational_load,
                drivers.maintenance_level,
            ],
            dtype=torch.float32,
        )
        return float(self.correction_net(x).item())

    def physics_health(self, drivers: DriverVector, cross_component_factor: float) -> float:
        """Override in child classes with component-specific degradation logic."""
        raise NotImplementedError

    def derive_metrics(self, health: float, drivers: DriverVector) -> dict[str, float]:
        """Override in child classes with component-specific telemetry metrics."""
        raise NotImplementedError

    def forward(self, drivers: DriverVector, cross_component_factor: float = 0.0) -> ComponentReport:
        base = self.physics_health(drivers, cross_component_factor)

        # Keep deterministic defaults by not using learned correction in inference.
        correction = 0.0
        health = self._clamp01(base + correction)

        return ComponentReport(
            component=self.component_name,
            health_index=health,
            operational_status=self._status_from_health(health),
            metrics=self.derive_metrics(health, drivers),
        )


@dataclass(frozen=True)
class ClassifierConfig:
    input_dim: int
    output_dim: int = 4
    hidden_dim: int = 128
    dropout: float = 0.15
    batch_size: int = 256
    epochs: int = 20
    lr: float = 1e-3
    weight_decay: float = 1e-4
    patience: int = 5
    grad_clip: float = 1.0
    seed: int = 42


class DenseClassifier(nn.Module):
    """Shared dense architecture for status-label classification."""

    def __init__(self, cfg: ClassifierConfig) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(cfg.input_dim, cfg.hidden_dim),
            nn.BatchNorm1d(cfg.hidden_dim),
            nn.ReLU(),
            nn.Dropout(cfg.dropout),
            nn.Linear(cfg.hidden_dim, cfg.hidden_dim),
            nn.ReLU(),
            nn.Dropout(cfg.dropout),
            nn.Linear(cfg.hidden_dim, cfg.output_dim),
        )
        self._init_weights()

    def _init_weights(self) -> None:
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.kaiming_uniform_(module.weight, nonlinearity="relu")
                nn.init.zeros_(module.bias)

    def forward(self, x: Tensor) -> Tensor:
        return self.net(x)


@torch.no_grad()
def evaluate_classifier(
    model: nn.Module, loader: DataLoader, criterion: nn.Module, device: torch.device
) -> tuple[float, float]:
    model.eval()
    total_loss = 0.0
    total_correct = 0
    total_samples = 0

    for xb, yb in loader:
        xb, yb = xb.to(device), yb.to(device)
        logits = model(xb)
        loss = criterion(logits, yb)

        total_loss += loss.item() * xb.size(0)
        total_correct += (logits.argmax(dim=1) == yb).sum().item()
        total_samples += xb.size(0)

    return total_loss / total_samples, total_correct / total_samples


def train_classifier(
    cfg: ClassifierConfig,
    train_loader: DataLoader,
    val_loader: DataLoader,
    class_weights: "Tensor | None" = None,
    component_name: str = "",
) -> tuple[DenseClassifier, dict[str, float]]:
    torch.manual_seed(cfg.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    use_amp = device.type == "cuda"
    model = DenseClassifier(cfg).to(device)

    weights_on_device = class_weights.to(device) if class_weights is not None else None
    criterion = nn.CrossEntropyLoss(weight=weights_on_device, label_smoothing=0.01)

    optimizer = DenseTrainingBase.build_optimizer(
        model, OptimizerConfig(lr=cfg.lr, weight_decay=cfg.weight_decay)
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=cfg.epochs)
    scaler = torch.amp.GradScaler(enabled=use_amp)

    best_val_loss = float("inf")
    best_val_acc = float("-inf")
    best_state: dict[str, Tensor] | None = None
    no_improve_epochs = 0

    prefix = f"[{component_name}] " if component_name else ""

    for epoch in range(1, cfg.epochs + 1):
        model.train()
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            optimizer.zero_grad(set_to_none=True)

            with torch.amp.autocast(device_type=device.type, enabled=use_amp):
                logits = model(xb)
                loss = criterion(logits, yb)

            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=cfg.grad_clip)
            scaler.step(optimizer)
            scaler.update()

        scheduler.step()
        val_loss, val_acc = evaluate_classifier(model, val_loader, criterion, device)

        print(
            f"{prefix}epoch {epoch:3d}/{cfg.epochs}  "
            f"val_loss={val_loss:.4f}  val_acc={val_acc:.4f}",
            flush=True,
        )

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_val_acc = val_acc
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
            no_improve_epochs = 0
        else:
            no_improve_epochs += 1

        if no_improve_epochs >= cfg.patience:
            print(f"{prefix}early stop at epoch {epoch}", flush=True)
            break

    if best_state is not None:
        model.load_state_dict(best_state)

    return model, {"val_loss": best_val_loss, "val_acc": best_val_acc}


# ─────────────────────────────────────────────────────────────
# Regression: predict health ∈ [0, 1] directly
# ─────────────────────────────────────────────────────────────

_HEALTH_THRESHOLDS = (0.70, 0.40, 0.20)


def health_to_label(health: np.ndarray) -> np.ndarray:
    """Map continuous health [0,1] → integer status label (0=FUNCTIONAL … 3=FAILED)."""
    labels = np.full(len(health), 3, dtype=np.int64)
    labels[health > 0.20] = 2
    labels[health > 0.40] = 1
    labels[health > 0.70] = 0
    return labels


@dataclass(frozen=True)
class RegressorConfig:
    input_dim: int
    hidden_dim: int = 128
    dropout: float = 0.15
    batch_size: int = 256
    epochs: int = 30
    lr: float = 1e-3
    weight_decay: float = 1e-4
    patience: int = 7
    grad_clip: float = 1.0
    seed: int = 42


class DenseRegressor(nn.Module):
    """Predicts component health ∈ [0, 1]. Label is derived by thresholding."""

    def __init__(self, cfg: RegressorConfig) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(cfg.input_dim, cfg.hidden_dim),
            nn.BatchNorm1d(cfg.hidden_dim),
            nn.ReLU(),
            nn.Dropout(cfg.dropout),
            nn.Linear(cfg.hidden_dim, cfg.hidden_dim),
            nn.ReLU(),
            nn.Dropout(cfg.dropout),
            nn.Linear(cfg.hidden_dim, 1),
            nn.Sigmoid(),
        )
        self._init_weights()

    def _init_weights(self) -> None:
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.kaiming_uniform_(module.weight, nonlinearity="relu")
                nn.init.zeros_(module.bias)

    def forward(self, x: Tensor) -> Tensor:
        return self.net(x).squeeze(1)


@torch.no_grad()
def evaluate_regressor(
    model: nn.Module, loader: DataLoader, device: torch.device
) -> tuple[float, float, float]:
    """Returns (mse, mae, derived_label_accuracy)."""
    model.eval()
    criterion = nn.MSELoss()
    total_mse = 0.0
    total_mae = 0.0
    total_samples = 0
    all_pred: list[np.ndarray] = []
    all_true: list[np.ndarray] = []

    for xb, yb in loader:
        xb, yb = xb.to(device), yb.to(device)
        pred = model(xb)
        total_mse += criterion(pred, yb).item() * xb.size(0)
        total_mae += (pred - yb).abs().mean().item() * xb.size(0)
        total_samples += xb.size(0)
        all_pred.append(pred.cpu().numpy())
        all_true.append(yb.cpu().numpy())

    pred_arr = np.concatenate(all_pred)
    true_arr = np.concatenate(all_true)
    derived_acc = float((health_to_label(pred_arr) == health_to_label(true_arr)).mean())
    return total_mse / total_samples, total_mae / total_samples, derived_acc


def train_regressor(
    cfg: RegressorConfig,
    train_loader: DataLoader,
    val_loader: DataLoader,
    component_name: str = "",
) -> tuple[DenseRegressor, dict[str, float]]:
    torch.manual_seed(cfg.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    use_amp = device.type == "cuda"
    model = DenseRegressor(cfg).to(device)
    criterion = nn.MSELoss()
    optimizer = DenseTrainingBase.build_optimizer(
        model, OptimizerConfig(lr=cfg.lr, weight_decay=cfg.weight_decay)
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=cfg.epochs)
    scaler = torch.amp.GradScaler(enabled=use_amp)

    best_val_mse = float("inf")
    best_metrics: dict[str, float] = {}
    best_state: dict[str, Tensor] | None = None
    no_improve_epochs = 0
    prefix = f"[{component_name}] " if component_name else ""

    for epoch in range(1, cfg.epochs + 1):
        model.train()
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            optimizer.zero_grad(set_to_none=True)
            with torch.amp.autocast(device_type=device.type, enabled=use_amp):
                pred = model(xb)
                loss = criterion(pred, yb)
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=cfg.grad_clip)
            scaler.step(optimizer)
            scaler.update()

        scheduler.step()
        val_mse, val_mae, val_acc = evaluate_regressor(model, val_loader, device)
        print(
            f"{prefix}epoch {epoch:3d}/{cfg.epochs}  "
            f"val_mse={val_mse:.5f}  val_mae={val_mae:.4f}  derived_acc={val_acc:.4f}",
            flush=True,
        )

        if val_mse < best_val_mse:
            best_val_mse = val_mse
            best_metrics = {"val_mse": val_mse, "val_mae": val_mae, "val_acc": val_acc}
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
            no_improve_epochs = 0
        else:
            no_improve_epochs += 1

        if no_improve_epochs >= cfg.patience:
            print(f"{prefix}early stop at epoch {epoch}", flush=True)
            break

    if best_state is not None:
        model.load_state_dict(best_state)
    return model, best_metrics


__all__ = [
    "ClassifierConfig",
    "ComponentReport",
    "DenseClassifier",
    "DenseRegressor",
    "DenseTrainingBase",
    "DriverVector",
    "OperationalStatus",
    "OptimizerConfig",
    "RegressorConfig",
    "evaluate_classifier",
    "evaluate_regressor",
    "health_to_label",
    "train_classifier",
    "train_regressor",
]
