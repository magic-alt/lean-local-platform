import sys
import types

from .core.config import (
    ALGORITHM_PATH,
    DATA_DIR,
    DEFAULT_DOCKER_IMAGE,
    DEFAULT_RESEARCH_IMAGE,
    HOST_DATA_DIR,
    HOST_PLATFORM_DIR,
    OBJECT_STORE_DIR,
    PLATFORM_DIR,
    PLOT_SCRIPT,
    REPO_ROOT,
)
from .lean_engine import *
from .lean_engine import data_paths as _data_paths
from .lean_engine import data_writers as _data_writers
from .lean_engine import docker as _docker
from .lean_engine import reports as _reports
from .lean_engine import research as _research

shutil = _docker.shutil


_SYNC_TARGETS = {
    "ALGORITHM_PATH": (_docker,),
    "DATA_DIR": (_data_paths, _docker, _research),
    "DEFAULT_DOCKER_IMAGE": (_docker,),
    "DEFAULT_RESEARCH_IMAGE": (_research,),
    "HOST_DATA_DIR": (_docker,),
    "HOST_PLATFORM_DIR": (_docker,),
    "OBJECT_STORE_DIR": (_docker, _research),
    "PLATFORM_DIR": (_docker,),
    "PLOT_SCRIPT": (_reports,),
    "REPO_ROOT": (_data_paths, _data_writers, _docker, _reports, _research),
}


class _LeanCompatModule(types.ModuleType):
    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        for target in _SYNC_TARGETS.get(name, ()):
            setattr(target, name, value)


sys.modules[__name__].__class__ = _LeanCompatModule
