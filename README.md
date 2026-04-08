# hydra-apptainer-launcher

A minimal [Hydra](https://hydra.cc) launcher plugin that enables
[submitit](https://github.com/facebookincubator/submitit) SLURM jobs to run
inside an [Apptainer](https://apptainer.org) container on HPC clusters.

## The problem

`submitit.SlurmExecutor.__init__()` accepts a `python` parameter that overrides
the Python executable used in the generated sbatch script — the correct hook for
Apptainer. The stock `hydra-submitit-launcher 1.2.0` never forwards this
parameter to the executor constructor. This plugin fixes that with a one-line
change.

## Installation

```bash
pip install git+https://github.com/sgh14/hydra-apptainer-launcher
```

Or with `uv`:

```bash
uv add "hydra-apptainer-launcher @ git+https://github.com/sgh14/hydra-apptainer-launcher"
```

## Usage

Use `hydra/launcher=submitit_slurm_apptainer` and set `hydra.launcher.python`
to your Apptainer command:

```bash
python my_app.py -m \
    hydra/launcher=submitit_slurm_apptainer \
    hydra.launcher.python="apptainer exec --nv /path/to/image.sif python" \
    hydra.launcher.timeout_min=60 \
    hydra.launcher.slurm_partition=gpu \
    hydra.launcher.slurm_gres="gpu:1" \
    param=1,2,3
```

When `python` is omitted, the launcher behaves identically to the stock
`SlurmLauncher`.

## YAML config

For repeated use, define a Hydra launcher config in your project:

```yaml
# conf/hydra/launcher/slurm_apptainer_gpu.yaml
defaults:
  - submitit_slurm_apptainer

python: "apptainer exec --nv containers/my-image.sif python"
timeout_min: 120
slurm_partition: gpu
slurm_gres: "gpu:1"
slurm_mem_gb: 16
slurm_cpus_per_task: 4
```

Then run:

```bash
python my_app.py -m hydra/launcher=slurm_apptainer_gpu param=1,2,3
```

## Compatibility

| Package | Version |
|---|---|
| `hydra-core` | `>=1.3` |
| `hydra-submitit-launcher` | `>=1.2.0` |
| `submitit` | `>=1.3.3` (transitive) |
| Python | `>=3.10` |
