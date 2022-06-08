"""Objects that define how data is recorded from simulation."""
from abc import ABC, abstractmethod
from typing import Union, Tuple

import pydantic
import numpy as np

from .types import Literal, Ax, EMField, ArrayLike, Bound, FreqArray, Direction, Coordinate, Axis
from .geometry import Box
from .medium import Medium
from .validators import assert_plane
from .base import cached_property
from .mode import ModeSpec
from .viz import PlotParams, plot_params_monitor, ARROW_COLOR_MONITOR, ARROW_ALPHA
from ..log import SetupError, log, DataError
from ..constants import HERTZ, SECOND, MICROMETER, RADIAN


BYTES_REAL = 4
BYTES_COMPLEX = 8


class Monitor(Box, ABC):
    """Abstract base class for monitors."""

    name: str = pydantic.Field(
        ...,
        title="Name",
        description="Unique name for monitor.",
        min_length=1,
    )

    @cached_property
    def plot_params(self) -> PlotParams:
        """Default parameters for plotting a Monitor object."""
        return plot_params_monitor

    @cached_property
    def geometry(self) -> Box:
        """:class:`Box` representation of monitor.

        Returns
        -------
        :class:`Box`
            Representation of the monitor geometry as a :class:`Box`.
        """
        return Box(center=self.center, size=self.size)

    @abstractmethod
    def storage_size(self, num_cells: int, tmesh: ArrayLike[float, 1]) -> int:
        """Size of monitor storage given the number of points after discretization.

        Parameters
        ----------
        num_cells : int
            Number of grid cells within the monitor after discretization by a :class:`Simulation`.
        tmesh : Array
            The discretized time mesh of a :class:`Simulation`.

        Returns
        -------
        int
            Number of bytes to be stored in monitor.
        """


class FreqMonitor(Monitor, ABC):
    """:class:`Monitor` that records data in the frequency-domain."""

    freqs: FreqArray = pydantic.Field(
        ...,
        title="Frequencies",
        description="Array or list of frequencies stored by the field monitor.",
        units=HERTZ,
    )


class TimeMonitor(Monitor, ABC):
    """:class:`Monitor` that records data in the time-domain."""

    start: pydantic.NonNegativeFloat = pydantic.Field(
        0.0,
        title="Start time",
        description="Time at which to start monitor recording.",
        units=SECOND,
    )

    stop: pydantic.NonNegativeFloat = pydantic.Field(
        None,
        title="Stop time",
        description="Time at which to stop monitor recording.  "
        "If not specified, record until end of simulation.",
        units=SECOND,
    )

    interval: pydantic.PositiveInt = pydantic.Field(
        1,
        title="Time interval",
        description="Number of time step intervals between monitor recordings.",
    )

    @pydantic.validator("stop", always=True, allow_reuse=True)
    def stop_greater_than_start(cls, val, values):
        """Ensure sure stop is greater than or equal to start."""
        start = values.get("start")
        if val and val < start:
            raise SetupError("Monitor start time is greater than stop time.")
        return val

    def time_inds(self, tmesh: ArrayLike[float, 1]) -> Tuple[int, int]:
        """Compute the starting and stopping index of the monitor in a given discrete time mesh."""

        tind_beg, tind_end = (0, 0)

        if tmesh.size == 0:
            return (tind_beg, tind_end)

        # If monitor.stop is None, record until the end
        t_stop = self.stop
        if t_stop is None:
            tind_end = int(tmesh.size)
            t_stop = tmesh[-1]
        else:
            tend = np.nonzero(tmesh <= t_stop)[0]
            if tend.size > 0:
                tind_end = int(tend[-1] + 1)

        # Step to compare to in order to handle t_start = t_stop
        dt = 1e-20 if np.array(tmesh).size < 2 else tmesh[1] - tmesh[0]
        # If equal start and stopping time, record one time step
        if np.abs(self.start - t_stop) < dt:
            tind_beg = max(tind_end - 1, 0)
        else:
            tbeg = np.nonzero(tmesh[:tind_end] >= self.start)[0]
            tind_beg = tbeg[0] if tbeg.size > 0 else tind_end
        return (tind_beg, tind_end)

    def num_steps(self, tmesh: ArrayLike[float, 1]) -> int:
        """Compute number of time steps for a time monitor."""

        tind_beg, tind_end = self.time_inds(tmesh)
        return int((tind_end - tind_beg) / self.interval)


class AbstractFieldMonitor(Monitor, ABC):
    """:class:`Monitor` that records electromagnetic field data as a function of x,y,z."""

    fields: Tuple[EMField, ...] = pydantic.Field(
        ["Ex", "Ey", "Ez", "Hx", "Hy", "Hz"],
        title="Field Components",
        description="Collection of field components to store in the monitor.",
    )

    interval_space: Tuple[
        pydantic.PositiveInt, pydantic.PositiveInt, pydantic.PositiveInt
    ] = pydantic.Field(
        (1, 1, 1),
        title="Spatial interval",
        description="Number of grid step intervals between monitor recordings. If equal to 1, "
        "there will be no downsampling. If greater than 1, fields will be downsampled "
        "and automatically colocated.",
    )

    colocate: bool = pydantic.Field(
        None,
        title="Colocate fields",
        description="Toggle whether fields should be colocated to grid cell centers. Default: "
        "``False`` if ``interval_space`` is 1 in each direction, ``True`` if ``interval_space`` "
        "is greater than one in any direction.",
    )

    @pydantic.validator("colocate", always=True)
    def set_default_colocate(cls, val, values):
        """Toggle default field colocation setting based on `interval_space`."""
        interval_space = values.get("interval_space")
        if val is None:
            val = sum(interval_space) != 3
        return val

    def downsampled_num_cells(self, num_cells: Tuple[int, int, int]) -> Tuple[int, int, int]:
        """Given a tuple of the number of cells spanned by the monitor along each dimension,
        return the number of cells one would have after downsampling based on ``interval_space``.
        """
        num_cells_new = list(num_cells.copy())
        for idx, interval in enumerate(self.interval_space):
            if interval == 1 or num_cells[idx] < 4 or (num_cells[idx] - 1) <= interval:
                continue
            num_cells_new[idx] = np.floor((num_cells[idx] - 1) / interval) + 1
            num_cells_new[idx] += int((num_cells[idx] - 1) % interval > 0)
        return num_cells_new


class PlanarMonitor(Monitor, ABC):
    """:class:`Monitor` that has a planar geometry."""

    _plane_validator = assert_plane()


class AbstractFluxMonitor(PlanarMonitor, ABC):
    """:class:`Monitor` that records flux through a plane."""


class AbstractModeMonitor(PlanarMonitor, FreqMonitor):
    """:class:`Monitor` that records mode-related data."""

    mode_spec: ModeSpec = pydantic.Field(
        ...,
        title="Mode Specification",
        description="Parameters to feed to mode solver which determine modes measured by monitor.",
    )

    def plot(  # pylint:disable=too-many-arguments
        self,
        x: float = None,
        y: float = None,
        z: float = None,
        ax: Ax = None,
        sim_bounds: Bound = None,
        **patch_kwargs,
    ) -> Ax:

        # call the monitor.plot() function first
        ax = super().plot(x=x, y=y, z=z, ax=ax, **patch_kwargs)

        kwargs_alpha = patch_kwargs.get("alpha")
        arrow_alpha = ARROW_ALPHA if kwargs_alpha is None else kwargs_alpha

        # and then add an arrow using the direction comuputed from `_dir_arrow`.
        ax = self._plot_arrow(
            x=x,
            y=y,
            z=z,
            ax=ax,
            direction=self._dir_arrow,
            color=ARROW_COLOR_MONITOR,
            alpha=arrow_alpha,
            both_dirs=True,
            sim_bounds=sim_bounds,
        )
        return ax

    @cached_property
    def _dir_arrow(self) -> Tuple[float, float, float]:
        """Source direction normal vector in cartesian coordinates."""
        dx = np.cos(self.mode_spec.angle_phi) * np.sin(self.mode_spec.angle_theta)
        dy = np.sin(self.mode_spec.angle_phi) * np.sin(self.mode_spec.angle_theta)
        dz = np.cos(self.mode_spec.angle_theta)
        return self.unpop_axis(dz, (dx, dy), axis=self.size.index(0.0))


class FieldMonitor(AbstractFieldMonitor, FreqMonitor):
    """:class:`Monitor` that records electromagnetic fields in the frequency domain.

    Example
    -------
    >>> monitor = FieldMonitor(
    ...     center=(1,2,3),
    ...     size=(2,2,2),
    ...     fields=['Hx'],
    ...     freqs=[250e12, 300e12],
    ...     name='steady_state_monitor')
    """

    _data_type: Literal["FieldData"] = pydantic.Field("FieldData")

    def storage_size(self, num_cells: int, tmesh: ArrayLike[float, 1]) -> int:
        # stores 1 complex number per grid cell, per frequency, per field
        return BYTES_COMPLEX * num_cells * len(self.freqs) * len(self.fields)


class FieldTimeMonitor(AbstractFieldMonitor, TimeMonitor):
    """:class:`Monitor` that records electromagnetic fields in the time domain.

    Example
    -------
    >>> monitor = FieldTimeMonitor(
    ...     center=(1,2,3),
    ...     size=(2,2,2),
    ...     fields=['Hx'],
    ...     start=1e-13,
    ...     stop=5e-13,
    ...     interval=2,
    ...     name='movie_monitor')
    """

    _data_type: Literal["FieldTimeData"] = pydantic.Field("FieldTimeData")

    def storage_size(self, num_cells: int, tmesh: ArrayLike[float, 1]) -> int:
        # stores 1 real number per grid cell, per time step, per field
        num_steps = self.num_steps(tmesh)
        return BYTES_REAL * num_steps * num_cells * len(self.fields)


class PermittivityMonitor(FreqMonitor):
    """:class:`Monitor` that records the diagonal components of the complex-valued relative
    permittivity tensor in the frequency domain. The recorded data has the same shape as a
    :class:`.FieldMonitor` of the same geometry: the permittivity values are saved at the
    Yee grid locations, and can be interpolated to any point inside the monitor.

    Example
    -------
    >>> monitor = PermittivityMonitor(
    ...     center=(1,2,3),
    ...     size=(2,2,2),
    ...     freqs=[250e12, 300e12],
    ...     name='eps_monitor')
    """

    _data_type: Literal["PermittivityData"] = pydantic.Field("PermittivityData")

    def storage_size(self, num_cells: int, tmesh: ArrayLike[float, 1]) -> int:
        # stores 3 complex number per grid cell, per frequency
        return BYTES_COMPLEX * num_cells * len(self.freqs) * 3


class FluxMonitor(AbstractFluxMonitor, FreqMonitor):
    """:class:`Monitor` that records power flux through a plane in the frequency domain.

    Example
    -------
    >>> monitor = FluxMonitor(
    ...     center=(1,2,3),
    ...     size=(2,2,0),
    ...     freqs=[200e12, 210e12],
    ...     name='flux_monitor')
    """

    _data_type: Literal["FluxData"] = pydantic.Field("FluxData")

    def storage_size(self, num_cells: int, tmesh: ArrayLike[float, 1]) -> int:
        # stores 1 real number per frequency
        return BYTES_REAL * len(self.freqs)


class FluxTimeMonitor(AbstractFluxMonitor, TimeMonitor):
    """:class:`Monitor` that records power flux through a plane in the time domain.

    Example
    -------
    >>> monitor = FluxTimeMonitor(
    ...     center=(1,2,3),
    ...     size=(2,2,0),
    ...     start=1e-13,
    ...     stop=5e-13,
    ...     interval=2,
    ...     name='flux_vs_time')
    """

    _data_type: Literal["FluxTimeData"] = pydantic.Field("FluxTimeData")

    def storage_size(self, num_cells: int, tmesh: ArrayLike[float, 1]) -> int:
        # stores 1 real number per time tep
        num_steps = self.num_steps(tmesh)
        return BYTES_REAL * num_steps


class ModeMonitor(AbstractModeMonitor):
    """:class:`Monitor` that records amplitudes from modal decomposition of fields on plane.

    Example
    -------
    >>> mode_spec = ModeSpec(num_modes=3)
    >>> monitor = ModeMonitor(
    ...     center=(1,2,3),
    ...     size=(2,2,0),
    ...     freqs=[200e12, 210e12],
    ...     mode_spec=mode_spec,
    ...     name='mode_monitor')
    """

    _data_type: Literal["ModeData"] = pydantic.Field("ModeData")

    def storage_size(self, num_cells: int, tmesh: int) -> int:
        # stores 3 complex numbers per frequency, per mode.
        return 3 * BYTES_COMPLEX * len(self.freqs) * self.mode_spec.num_modes


class ModeFieldMonitor(AbstractModeMonitor):
    """:class:`Monitor` that stores the mode field profiles returned by the mode solver in the
    monitor plane.

    Example
    -------
    >>> mode_spec = ModeSpec(num_modes=3)
    >>> monitor = ModeFieldMonitor(
    ...     center=(1,2,3),
    ...     size=(2,2,0),
    ...     freqs=[200e12, 210e12],
    ...     mode_spec=mode_spec,
    ...     name='mode_monitor')
    """

    _data_type: Literal["ModeFieldData"] = pydantic.Field("ModeFieldData")

    def storage_size(self, num_cells: int, tmesh: int) -> int:
        return 6 * BYTES_COMPLEX * num_cells * len(self.freqs) * self.mode_spec.num_modes


class Near2FarMonitor(AbstractFieldMonitor, FreqMonitor):
    """:class:`Monitor` that samples electromagnetic near fields in the frequency domain
       and invokes the computation of far fields at predefined angles.

    Example
    -------
    >>> monitor = Near2FarMonitor(
    ...     center=(1,2,3),
    ...     size=(2,2,0),
    ...     freqs=[250e12, 300e12],
    ...     name='far_field_monitor',
    ...     local_origin=(1,2,3),
    ...     angles_phi=[0, np.pi/2],
    ...     angles_theta=np.linspace(-np.pi/2, np.pi/2, 100)
    ...     )
    """

    _data_type: Literal["Near2FarData"] = pydantic.Field("Near2FarData")

    angles_theta: List[float] = pydantic.Field(
        ...,
        title="Polar Angles",
        description="Polar angles relative to ``local_origin`` at which to compute far fields.",
        units=RADIAN,
    )

    angles_phi: List[float] = pydantic.Field(
        ...,
        title="Azimuth Angles",
        description="Azimuth angles relative to ``local_origin`` at which to compute far fields.",
        units=RADIAN,
    )

    normal_dir: Direction = pydantic.Field(
        None,
        title="Normal vector orientation",
        description=":class:`.Direction` of the surface monitor's normal vector w.r.t. "
        "the positive x, y or z unit vectors. Must be one of '+' or '-'.",
    )

    custom_origin: Coordinate = pydantic.Field(
        None,
        title="Local origin",
        description="Local origin used for defining observation points. If ``None``, uses the "
        "monitor's center.",
        units=MICROMETER,
    )

    exclude_surfaces: List[Literal["x-", "x+", "y-", "y+", "z-", "z+"]] = pydantic.Field(
        None,
        title="Excluded surfaces",
        description="Surfaces to exclude during the near-to-far projection.",
    )

    medium: Medium = pydantic.Field(
        Medium(permittivity=1),
        title="Background medium",
        description="Background medium in which to radiate near fields to far fields. "
        "If not provided, uses free space.",
    )

    @pydantic.root_validator()
    def normal_dir_exists_for_surface(cls, values):
        """If the monitor is a surface, set default ``normal_dir`` if not provided.
        If the monitor is a box, warn that ``normal_dir`` is relevant only for surfaces."""
        normal_dir = values.get("normal_dir")
        name = values.get("name")
        size = values.get("size")
        if size.count(0.0) != 1:
            if normal_dir is not None:
                log.warning(
                        "The ``normal_dir`` field is relevant only for surface monitors "
                        f"and will be ignored for monitor {name}, which is a box."
                    )
        else:
            if normal_dir is None:
                raise SetupError(
                    f"Must specify ``normal_dir`` for surface monitor {name}."
                )
        return values

    @pydantic.root_validator()
    def check_excluded_surfaces(cls, values):
        """Error if ``exclude_surfaces`` is provided for a surface monitor."""
        exclude_surfaces = values.get("exclude_surfaces")
        if exclude_surfaces is None:
            return values
        name = values.get("name")
        size = values.get("size")
        if size.count(0.0) > 0:
            raise SetupError(
                f"Can't specify ``exclude_surfaces`` for surface monitor {name}; "
                "valid for box monitors only."
            )
        return values

    @property
    def axis(self) -> Axis:
        """Returns the :class:`.Axis` normal to this surface."""
        # assume that the monitor's axis is in the direction where the monitor is thinnest
        # and errors if the monitor is a box
        if self.size.count(0.0) != 1:
            raise DataError(
                "Requested ``axis`` property for a box monitor; ``axis`` is defined "
                "for surface monitors only."
                )
        return self.size.index(0.0)

    @property
    def local_origin(self) -> Coordinate:
        """Returns the local origin associated with this monitor."""
        if self.custom_origin is None:
            return self.center
        return self.custom_origin

    def storage_size(self, num_cells: int, tmesh: Array) -> int:
        # stores 1 complex number per pair of angles, per frequency, 
        # for N_theta, N_phi, L_theta, and L_phi (4 components)
        return BYTES_COMPLEX * \
            len(self.angles_theta) * len(self.angles_phi) * len(self.freqs) * 4

    @staticmethod
    def angles_from_cartesian_points(
        x: List[float], y: List[float], z: List[float]
        ) -> List[List[float]]:
        """Get a list of linearly spaced angles which are guaranteed to span the space
        occupied by a given set of points in Cartesian coordinates. The lists of angles
        will have as many points as the largest number of Cartesian points provided
        along any dimension.

        Parameters
        ----------
        x : List[float]
            x coordinates relative to ``local_origin``.
        y : List[float]
            y coordinates relative to ``local_origin``.
        z : List[float]
            z coordinates relative to ``local_origin``.

        Returns
        -------
        theta : List[float]
            theta coordinates relative to ``local_origin``.
        phi : List[float]
            phi coordinates relative to ``local_origin``.
        """
        points_grid = np.meshgrid(x, y, z)
        x, y, z = [points.flatten() for points in points_grid]

        _, theta, phi = Near2FarMonitor.car_2_sph(x, y, z)
        theta = np.linspace(np.min(theta), np.max(theta), np.max(points_grid[0].shape))
        phi = np.linspace(np.min(phi), np.max(phi), np.max(points_grid[0].shape))
        return list(theta), list(phi)

    @staticmethod
    def car_2_sph(x: float, y: float, z: float):
        """Convert Cartesian to spherical coordinates.

        Parameters
        ----------
        x : float
            x coordinate relative to ``local_origin``.
        y : float
            y coordinate relative to ``local_origin``.
        z : float
            z coordinate relative to ``local_origin``.

        Returns
        -------
        r : float
            r coordinate relative to ``local_origin``.
        theta : float
            theta coordinate relative to ``local_origin``.
        phi : float
            phi coordinate relative to ``local_origin``.
        """
        r = np.sqrt(x**2 + y**2 + z**2)
        theta = np.arccos(z / r)
        phi = np.arctan2(y, x)
        return r, theta, phi

    @staticmethod
    def sph_2_car(r, theta, phi):
        """Convert spherical to Cartesian coordinates.

        Parameters
        ----------
        r : float
            radius.
        theta : float
            polar angle (rad) downward from x=y=0 line.
        phi : float
            azimuthal (rad) angle from y=z=0 line.

        Returns
        -------
        x : float
            x coordinate relative to ``local_origin``.
        y : float
            y coordinate relative to ``local_origin``.
        z : float
            z coordinate relative to ``local_origin``.
        """
        r_sin_theta = r * np.sin(theta)
        x = r_sin_theta * np.cos(phi)
        y = r_sin_theta * np.sin(phi)
        z = r * np.cos(theta)
        return x, y, z


# types of monitors that are accepted by simulation
MonitorType = Union[
    FieldMonitor,
    Near2FarMonitor,
    FieldTimeMonitor,
    PermittivityMonitor,
    FluxMonitor,
    FluxTimeMonitor,
    ModeMonitor,
    ModeFieldMonitor,
    # Near2FarMonitor,
]


