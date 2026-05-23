# Local Environment

## Status

Environment setup was verified on a Windows desktop with Python 3.11, CUDA-enabled PyTorch, and an NVIDIA RTX 3060 Ti.

Use a project-local virtual environment for a fresh clone:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt
```

Activate from PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Run Python directly without activation:

```powershell
.\.venv\Scripts\python
```

## Why Venv Instead Of Conda

Conda was attempted first on the original machine, but the local Anaconda base install could not load OpenSSL:

```text
CondaSSLError: OpenSSL appears to be unavailable on this machine.
```

A standard Python 3.11 virtual environment worked cleanly. The repo now ignores `.venv/`, `venv/`, and `env/` so dependency files do not get committed.

## Verified Package Stack

```text
Python 3.11.9
torch 2.11.0+cu128
torch CUDA runtime 12.8
CUDA available: True
GPU: NVIDIA GeForce RTX 3060 Ti
transformers 5.9.0
datasets 4.8.5
accelerate 1.13.0
```

`pip check` reported no broken requirements on the original setup.

## Smoke Test Result

A small CUDA tensor/backpropagation test completed successfully:

```text
final_loss: 1.032284
elapsed_seconds: 1.219
peak_allocated_vram_mb: 30.52
```

This proves CUDA PyTorch can use the RTX 3060 Ti. It does not prove that large model training will fit; that depends on sequence length, batch size, precision, optimizer state, and checkpoint policy.

## Observed Machine Headroom

Before setup:

```text
C: free disk: about 342.98 GB
Free RAM: about 20.96 GB
GPU VRAM free: about 7314 MB of 8192 MB
```

After setup:

```text
C: free disk: about 334.06 GB
Venv size: about 4.86 GB
Pip cache size: about 13.65 GB
GPU idle VRAM free: about 7335 MB of 8192 MB
```

The pip cache includes previously cached packages too. It can be cleared later, but keeping it helps avoid repeated downloads.

## Actual Setup Downloads

The largest single download was PyTorch:

```text
torch-2.11.0+cu128: 2753.1 MB
torchvision-0.26.0+cu128: 9.3 MB
torchaudio-2.11.0+cu128: 1.7 MB
```

The remaining ML/data packages were much smaller individually. Notable downloads included `pyarrow` at 27.3 MB and `scipy` at 36.6 MB.

Total practical setup impact:

- Downloaded: roughly 3 GB during this run, plus reuse of existing pip cache.
- Installed venv: about 4.86 GB.
- Disk remaining on the original setup: about 334 GB.

## Repeat The Environment Check

```powershell
.\.venv\Scripts\python scripts\check_environment.py
```
