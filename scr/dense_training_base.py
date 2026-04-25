from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import torch
from torch import Tensor, nn
from torch.utils.data import DataLoader


@dataclass
class TrainConfig:
    input_dim: int
    output_dim: int
    hidden_dim: int = 128
    dropout: float = 0.2
    batch_size: int = 64
    epochs: int = 50
    lr: float = 1e-3
    weight_decay: float = 1e-4
    patience: int = 8
    grad_clip: float = 1.0
    seed: int = 42


class DenseModel(nn.Module):
    def __init__(
        self, input_dim: int, hidden_dim: int, output_dim: int, dropout: float
    ) -> None:
        super().__init__()

        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.BatchNorm1d(hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, output_dim),
        )

        self._init_weights()

    def _init_weights(self) -> None:
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.kaiming_uniform_(module.weight, nonlinearity="relu")
                nn.init.zeros_(module.bias)

    def forward(self, x: Tensor) -> Tensor:
        return self.net(x)


def build_dataloaders(cfg: TrainConfig) -> Tuple[DataLoader, DataLoader]:
    """
    Reemplaza esta función con tu pipeline real de dataset.

    Esperado:
    - train_loader: batches de (x, y)
    - val_loader: batches de (x, y)

    x: Tensor de forma [batch, cfg.input_dim]
    y: Tensor de etiquetas enteras para clasificación [batch]
    """
    raise NotImplementedError("Implementa aquí tu carga de dataset real.")


@torch.no_grad()
def evaluate(
    model: nn.Module, loader: DataLoader, criterion: nn.Module, device: torch.device
) -> Tuple[float, float]:
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


def train(
    cfg: TrainConfig, train_loader: DataLoader, val_loader: DataLoader
) -> DenseModel:
    torch.manual_seed(cfg.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    use_amp = device.type == "cuda"

    model = DenseModel(cfg.input_dim, cfg.hidden_dim, cfg.output_dim, cfg.dropout).to(
        device
    )

    criterion = nn.CrossEntropyLoss(label_smoothing=0.05)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=cfg.epochs)
    scaler = torch.amp.GradScaler(enabled=use_amp)

    best_val_loss = float("inf")
    best_state = None
    no_improve_epochs = 0

    for epoch in range(1, cfg.epochs + 1):
        model.train()
        running_loss = 0.0

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

            running_loss += loss.item() * xb.size(0)

        scheduler.step()

        train_loss = running_loss / len(train_loader.dataset)
        val_loss, val_acc = evaluate(model, val_loader, criterion, device)

        print(
            f"Epoch {epoch:02d}/{cfg.epochs} | "
            f"train_loss={train_loss:.4f} | val_loss={val_loss:.4f} | val_acc={val_acc:.4f}"
        )

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
            no_improve_epochs = 0
        else:
            no_improve_epochs += 1

        if no_improve_epochs >= cfg.patience:
            print(f"Early stopping activado en epoch {epoch}.")
            break

    if best_state is not None:
        model.load_state_dict(best_state)

    return model


def main() -> None:
    cfg = TrainConfig(
        input_dim=32,
        output_dim=5,
        hidden_dim=128,
        dropout=0.25,
    )

    print(
        "Base creada. Implementa build_dataloaders(cfg) y luego llama a train(cfg, train_loader, val_loader)."
    )
    print(DenseModel(cfg.input_dim, cfg.hidden_dim, cfg.output_dim, cfg.dropout))


if __name__ == "__main__":
    main()
