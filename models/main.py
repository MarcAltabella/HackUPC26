import torch


def main():
    print(f"Torch version: {torch.__version__}")
    print(f"CUDA disponible: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        idx = torch.cuda.current_device()
        print(f"GPU index: {idx}")
        print(f"GPU nombre: {torch.cuda.get_device_name(idx)}")
        print(f"CUDA runtime (torch): {torch.version.cuda}")
    else:
        print("No se detecta GPU/CUDA en PyTorch.")


if __name__ == "__main__":
    main()
