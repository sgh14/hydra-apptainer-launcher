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

### Bind-mounting SLURM into the container

On most clusters, SLURM binaries and the munge authentication stack are not installed
inside container images. When `submitit` calls `sbatch` (or `srun`) from inside
the container it will fail unless these host paths are visible inside it. Without
the necessary bind mounts, you will hit the following errors in sequence:

1. `RuntimeError: Could not detect "srun"` — SLURM binaries missing
2. `Invalid user for SlurmUser slurm` — `/etc/passwd` missing
3. `dlopen(auth_munge.so): libmunge.so.2: cannot open shared object file` — munge library missing
4. `Munge encode failed: Failed to access "/var/run/munge/munge.socket.2"` — munge socket missing

Additionally, any tool that writes temporary files to `$TMPDIR` (such as W&B artifact
uploads) will fail if the cluster's scratch filesystem is not visible inside the
container. SLURM sets `$TMPDIR` to a per-job subdirectory under the scratch mount
point (e.g. `/scratchdata/<user>/<jobid>/`) after the job starts. Binding the whole
mount point (e.g. `/scratchdata`) makes the per-job subdirectory visible
automatically without needing to know the job ID in advance.

#### Option 1 — `APPTAINER_BINDPATH` environment variable (recommended)

Apptainer reads the `APPTAINER_BINDPATH` environment variable at startup and
treats its value as a comma-separated list of paths to bind into the container
automatically — exactly like `--bind` flags but without requiring any flags in
the command itself.

Set `APPTAINER_BINDPATH` in your shell environment or project `.env` file before
calling `apptainer exec`. SLURM propagates environment variables set at submission
time to compute nodes via `--export=ALL` (the default), so the variable is
inherited by the compute-node `apptainer exec` call in `hydra.launcher.python`
without any extra steps.

```bash
# In your project's hpc/.env (or equivalent)
# Replace /scratchdata with your cluster's scratch mount point.
# On clusters where Apptainer is configured globally (via apptainer.conf),
# this can be left empty.
export APPTAINER_BINDPATH="/usr/bin/sbatch,/usr/bin/srun,/usr/bin/squeue,/usr/bin/scancel,/usr/bin/scontrol,/usr/bin/sacct,/usr/lib64/slurm,/usr/lib64/libmunge.so.2,/var/run/munge,/etc/slurm,/etc/passwd,/etc/group,/scratchdata"
```

With this set, the `apptainer exec` calls in your dispatch script require no
`--bind` flags at all:

```bash
# dispatch script — no --bind flags needed anywhere
source hpc/.env   # exports APPTAINER_BINDPATH

apptainer exec /path/to/image.sif \
    my_app -m \
    hydra/launcher=submitit_slurm_apptainer \
    "hydra.launcher.python=apptainer exec /path/to/image.sif python" \
    hydra.launcher.partition=gpu \
    param=1,2,3
```

Both the login-node `apptainer exec` and the compute-node `apptainer exec`
(in `hydra.launcher.python`) inherit `APPTAINER_BINDPATH` from the environment
and apply the bind mounts automatically.

#### Option 2 — manual `--bind` flags

If you cannot set environment variables before calling `apptainer exec`, bind
the mounts manually. The same bind flags must appear in **both** places:
the outer `apptainer exec` call on the login node (so `sbatch` works there) and
the `hydra.launcher.python` value (so `srun` and `$TMPDIR` work on compute nodes):

```bash
BINDS="--bind /usr/bin/sbatch,/usr/bin/srun,/usr/bin/squeue,/usr/bin/scancel,/usr/bin/scontrol,/usr/bin/sacct,/usr/lib64/slurm,/usr/lib64/libmunge.so.2,/var/run/munge,/etc/slurm,/etc/passwd,/etc/group,/scratchdata"

apptainer exec ${BINDS} /path/to/image.sif \
    my_app -m \
    hydra/launcher=submitit_slurm_apptainer \
    "hydra.launcher.python=apptainer exec ${BINDS} /path/to/image.sif python" \
    hydra.launcher.partition=gpu \
    hydra.launcher.gres="gpu:1" \
    param=1,2,3
```

Note: adjust `/scratchdata` to your cluster's scratch mount point, and adjust
SLURM binary paths if your cluster installs them in non-standard locations
(e.g. `/usr/local/bin/` on Ubuntu-based clusters).

#### Option 3 — cluster-wide configuration (admin)

Ask the cluster admin to add the required paths to `/etc/apptainer/apptainer.conf`
as global `bind path =` entries. This eliminates the need for any per-user
configuration — the approach used by sites like NERSC and OLCF.

### Keeping the YAML cluster-agnostic

Hardcoding the container path in a YAML file ties the config to one machine.
A better pattern is to inject `hydra.launcher.python` dynamically from a shell
script that resolves the path at runtime, leaving the YAML portable:

> **Note:** You cannot compose `submitit_slurm_apptainer` on top of a `submitit_slurm`-based
> config using Hydra's `defaults` list — OmegaConf raises a `ConfigTypeError` at startup.
> All SLURM resource parameters must be inlined directly under `submitit_slurm_apptainer`.

```yaml
# conf/hydra/launcher/slurm-apptainer-gpu.yaml
defaults:
  - submitit_slurm_apptainer   # ← only this; do NOT prepend slurm-native-gpu

# All SLURM resource params inlined here:
partition: gpu
gres: "gpu:1"
mem_gb: 32
cpus_per_task: 8
timeout_min: 240
submitit_folder: ${hydra.sweep.dir}/.submitit/%j

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

### Avoiding resource duplication between native and Apptainer configs

> **Note:** You cannot compose `submitit_slurm_apptainer` on top of a `submitit_slurm`-based
> config using Hydra's `defaults` list. OmegaConf refuses to merge `SlurmQueueConf` with
> `ApptainerSlurmQueueConf` even though the latter is a Python subclass of the former.
> This means `defaults: [slurm-native-gpu, submitit_slurm_apptainer]` will raise a
> `ConfigTypeError` at startup.

The working pattern is to inline all SLURM resource parameters directly under
`submitit_slurm_apptainer` in each Apptainer config. When you need to change a resource
(partition, memory, timeout), update both the native and Apptainer YAMLs — or drop the
native variant entirely if you always use Apptainer:

```yaml
# conf/hydra/launcher/slurm-apptainer-gpu.yaml
defaults:
  - submitit_slurm_apptainer   # ← only this; do NOT prepend slurm-native-gpu

# All SLURM resource params inlined here:
partition: gpu
gres: "gpu:1"
mem_gb: 32
cpus_per_task: 8
timeout_min: 240
submitit_folder: ${hydra.sweep.dir}/.submitit/%j

# python is NOT set here — injected at call time by the dispatch script
```

### Argument ordering with `+hydra.searchpath`

If you use `+hydra.searchpath=[...]` to add extra config search paths, it must appear
**after** `-m` and all `hydra/launcher=` and `hydra.launcher.*` overrides:

```bash
# CORRECT — -m and launcher overrides first, +hydra.searchpath last
apptainer exec image.sif my_app \
    -m \
    hydra/launcher=submitit_slurm_apptainer \
    "hydra.launcher.python=apptainer exec image.sif python" \
    "+hydra.searchpath=[file:///path/to/extra/conf]" \
    param=1,2,3

# WRONG — +hydra.searchpath before -m causes argparse to fail
apptainer exec image.sif my_app \
    "+hydra.searchpath=[file:///path/to/extra/conf]" \
    -m \
    hydra/launcher=submitit_slurm_apptainer \
    param=1,2,3
```

This is a constraint of Hydra's `nargs='*'` positional argument parser, not specific to
this plugin.

## Compatibility

| Package | Version |
|---|---|
| `hydra-core` | `>=1.3` |
| `hydra-submitit-launcher` | `>=1.2.0` |
| `submitit` | `>=1.3.3` (transitive) |
| Python | `>=3.10` |
