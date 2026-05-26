"""Safe local environment check for the Missouri Public Data AI Assistant."""

from __future__ import annotations

import json
import platform
import shutil
import time

import psutil
import torch


def bytes_to_gb(value: int) -> float:
    return round(value / 1024**3, 2)


def main() -> None:
    disk = shutil.disk_usage("C:\\")
    memory = psutil.virtual_memory()

    result = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "disk_c_free_gb": bytes_to_gb(disk.free),
        "disk_c_total_gb": bytes_to_gb(disk.total),
        "ram_available_gb": bytes_to_gb(memory.available),
        "ram_total_gb": bytes_to_gb(memory.total),
        "torch": torch.__version__,
        "torch_cuda_runtime": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(),
    }

    if torch.cuda.is_available():
        device = torch.device("cuda")
        props = torch.cuda.get_device_properties(0)
        result["gpu_name"] = props.name
        result["gpu_total_vram_gb"] = round(props.total_memory / 1024**3, 2)

        torch.cuda.reset_peak_memory_stats()
        start = time.perf_counter()

        model = torch.nn.Sequential(
            torch.nn.Linear(512, 1024),
            torch.nn.GELU(),
            torch.nn.Linear(1024, 128),
        ).to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)

        for _ in range(10):
            x = torch.randn(256, 512, device=device)
            y = torch.randn(256, 128, device=device)
            optimizer.zero_grad(set_to_none=True)
            loss = torch.nn.functional.mse_loss(model(x), y)
            loss.backward()
            optimizer.step()

        result["smoke_final_loss"] = round(float(loss.detach().cpu()), 6)
        result["smoke_elapsed_seconds"] = round(time.perf_counter() - start, 3)
        result["smoke_peak_allocated_vram_mb"] = round(
            torch.cuda.max_memory_allocated() / 1024**2,
            2,
        )
        torch.cuda.empty_cache()

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
