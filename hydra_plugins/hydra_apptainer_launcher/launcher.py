"""ApptainerSlurmLauncher — Hydra SLURM launcher with Apptainer support.

Copied from hydra-submitit-launcher==1.2.0 SlurmLauncher.launch() with one
functional change: ``"python"`` is added to ``specific_init_keys`` so it is
forwarded to ``SlurmExecutor.__init__()`` rather than ``update_parameters()``.
This is the only mechanism that makes the Python executable on compute nodes
configurable, which is required for Apptainer wrapping.

When bumping hydra-submitit-launcher, check whether the upstream launch()
has changed and update this copy accordingly.
"""

import logging
import os
from pathlib import Path
from typing import Sequence

import submitit
from hydra.core.singleton import Singleton
from hydra.core.utils import JobReturn, filter_overrides
from hydra_plugins.hydra_submitit_launcher.config import BaseQueueConf
from hydra_plugins.hydra_submitit_launcher.submitit_launcher import (
    BaseSubmititLauncher,
)
from omegaconf import OmegaConf

from .config import (
    ApptainerSlurmQueueConf,  # noqa: F401 — triggers ConfigStore registration
)

log = logging.getLogger(__name__)


class ApptainerSlurmLauncher(BaseSubmititLauncher):
    """SLURM launcher that routes the ``python`` config key to
    ``SlurmExecutor.__init__()``, enabling Apptainer wrapping.

    Set ``hydra.launcher.python`` to the shell command that should be used as
    the Python executable on compute nodes, e.g.::

        hydra.launcher.python="apptainer exec --nv /path/to/image.sif python"

    When ``python`` is ``None`` (the default), behaviour is identical to the
    stock SlurmLauncher — submitit uses the current interpreter.
    """

    _EXECUTOR = "slurm"

    def launch(
        self,
        job_overrides: Sequence[Sequence[str]],
        initial_job_idx: int,
    ) -> Sequence[JobReturn]:
        assert self.config is not None
        assert len(job_overrides) > 0

        params = self.params
        init_params = {"folder": params["submitit_folder"]}

        # ---- patch: add "python" so it reaches SlurmExecutor.__init__() ----
        specific_init_keys = {"max_num_timeout", "python"}
        init_params.update(
            **{
                f"{self._EXECUTOR}_{x}": y
                for x, y in params.items()
                if x in specific_init_keys
                and y is not None  # skip None: don't override submitit default
            }
        )
        # ---------------------------------------------------------------------

        init_keys = specific_init_keys | {"submitit_folder"}
        executor = submitit.AutoExecutor(cluster=self._EXECUTOR, **init_params)

        baseparams = set(OmegaConf.structured(BaseQueueConf).keys())
        update_params = {
            x if x in baseparams else f"{self._EXECUTOR}_{x}": y
            for x, y in params.items()
            if x not in init_keys
        }
        executor.update_parameters(**update_params)

        log.info(
            f"Submitit '{self._EXECUTOR}' sweep output dir: "
            f"{self.config.hydra.sweep.dir}"
        )
        sweep_dir = Path(str(self.config.hydra.sweep.dir))
        sweep_dir.mkdir(parents=True, exist_ok=True)
        if "mode" in self.config.hydra.sweep:
            mode = int(str(self.config.hydra.sweep.mode), 8)
            os.chmod(sweep_dir, mode=mode)

        job_params = []
        for idx, overrides in enumerate(job_overrides):
            idx = initial_job_idx + idx
            lst = " ".join(filter_overrides(overrides))
            log.info(f"\t#{idx} : {lst}")
            job_params.append(
                (
                    list(overrides),
                    "hydra.sweep.dir",
                    idx,
                    f"job_id_for_{idx}",
                    Singleton.get_state(),
                )
            )

        jobs = executor.map_array(self, *zip(*job_params))
        return [j.results()[0] for j in jobs]
