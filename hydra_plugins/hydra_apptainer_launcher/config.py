from dataclasses import dataclass
from typing import Optional

from hydra.core.config_store import ConfigStore
from hydra_plugins.hydra_submitit_launcher.config import SlurmQueueConf


@dataclass
class ApptainerSlurmQueueConf(SlurmQueueConf):
    """Extends SlurmQueueConf with an Apptainer python-wrapper field.

    Set ``python`` to the shell command used to invoke Python on compute
    nodes, e.g. ``"apptainer exec --nv /path/to/image.sif python"``.
    When ``None`` (the default), behaviour is identical to the stock
    SlurmLauncher.
    """

    _target_: str = (
        "hydra_plugins.hydra_apptainer_launcher.launcher"
        ".ApptainerSlurmLauncher"
    )

    # Shell command to use as the Python executable on compute nodes.
    # Example: "apptainer exec --nv /path/to/nqs-tests-gpu.sif python"
    python: Optional[str] = None


ConfigStore.instance().store(
    group="hydra/launcher",
    name="submitit_slurm_apptainer",
    node=ApptainerSlurmQueueConf(),
    provider="hydra_apptainer_launcher",
)
