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

## Usage on clusters without a system Python

Some HPC clusters have neither Python nor pip available on login or compute nodes
— all software runs exclusively inside containers. This requires **two levels of
Apptainer wrapping**:

1. **Outer wrap** — the Hydra app itself (including submitit) runs inside a
   container on the login node.
2. **Inner wrap** — each SLURM task that submitit generates also runs inside a
   container on the compute node, via `hydra.launcher.python`.

```bash
apptainer exec /path/to/image.sif \
    my_app -m \
    hydra/launcher=submitit_slurm_apptainer \
    "hydra.launcher.python=apptainer exec --nv /path/to/image.sif python" \
    hydra.launcher.partition=gpu \
    hydra.launcher.gres="gpu:1" \
    param=1,2,3
```

### Keeping the YAML cluster-agnostic

Hardcoding the container path in a YAML file ties the config to one machine.
A better pattern is to inject `hydra.launcher.python` dynamically from a shell
script that resolves the path at runtime, leaving the YAML portable:

```yaml
# conf/hydra/launcher/slurm-apptainer-gpu.yaml
defaults:
  - slurm-native-gpu          # resource defaults (partition, mem, gres, …)
  - submitit_slurm_apptainer  # launcher type

# python is NOT set here — injected at call time by the dispatch script
```

```bash
# dispatch.sh (simplified)
CONTAINER_PATH="/path/to/containers/my-image-gpu.sif"

apptainer exec "${CONTAINER_PATH}" \
    my_app -m \
    hydra/launcher=slurm-apptainer-gpu \
    "hydra.launcher.python=apptainer exec --nv ${CONTAINER_PATH} python" \
    param=1,2,3
```

The container path is resolved once in the shell script from cluster-local config
(e.g. an `.env` file) rather than being hardcoded in a YAML that lives in the repo.

### Composing resource defaults from a base config

When you have both Apptainer and native SLURM variants, you can avoid duplicating
resource settings by composing the Apptainer config from a native base:

```yaml
# conf/hydra/launcher/slurm-native-gpu.yaml  — resource defaults only
defaults:
  - submitit_slurm

partition: gpu
gres: "gpu:1"
mem_gb: 32
cpus_per_task: 8
timeout_min: 240
```

```yaml
# conf/hydra/launcher/slurm-apptainer-gpu.yaml  — inherits all resources above
defaults:
  - slurm-native-gpu          # all resource values come from here
  - submitit_slurm_apptainer  # only the launcher type changes

# python injected at runtime by the dispatch script
```

`slurm-apptainer-gpu` inherits every resource value from `slurm-native-gpu` and
only overrides the launcher implementation. Resource tweaks (partition, memory,
timeout) only need to be made in one place regardless of whether Apptainer is used.

## Compatibility

| Package | Version |
|---|---|
| `hydra-core` | `>=1.3` |
| `hydra-submitit-launcher` | `>=1.2.0` |
| `submitit` | `>=1.3.3` (transitive) |
| Python | `>=3.10` |
