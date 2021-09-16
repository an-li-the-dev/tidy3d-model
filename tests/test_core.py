import pytest
import numpy as np
import pydantic

import sys
sys.path.append('./')

from tidy3d.plugins.data_analyzer import *
from tidy3d import *
from tidy3d_core.data import *

SIM = Simulation(
    size=(2.0, 2.0, 2.0),
    grid_size=.01,
    monitors={
        "field_freq": FieldMonitor(size=(1,1,1), center=(0,1,0), sampler=FreqSampler(freqs=[1,2, 5, 3, 3])),
        "field_time": FieldMonitor(size=(1,1,0), center=(1,0,0), sampler=TimeSampler(times=[1])),
        "flux_freq": FluxMonitor(size=(1,1,0), center=(0,0,0), sampler=FreqSampler(freqs=[1,2, 1, 5])),
        "flux_time": FluxMonitor(size=(1,1,0), center=(0,0,0), sampler=TimeSampler(times=[1,2, 3])),
        "mode": ModeMonitor(size=(1,1,0), center=(0,0,0), sampler=FreqSampler(freqs=[1.90,2.01, 2.0]), modes=[Mode(mode_index=1)])
    },
)

def test_load():
    sim_data = create_data(SIM)
    import pdb; pdb.set_trace()
