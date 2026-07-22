# License: MIT
# Copyright © 2025 Frequenz Energy-as-a-Service GmbH

"""Component graph generation and per-type queries over the Assets API.

The `ComponentGraphGenerator` builds a `MicrogridComponentGraph` from the
Platform Assets API. The module-level query functions (e.g. `pv_meter_ids`)
return component IDs read back out of such a graph.
"""

import logging
from collections.abc import Callable

from frequenz.client.assets import AssetsApiClient
from frequenz.client.assets.electrical_component import (
    Battery,
    BatteryInverter,
    Breaker,
    Chp,
    ComponentConnection,
    ElectricalComponent,
    EvCharger,
    GridConnectionPoint,
    Meter,
    SolarInverter,
)
from frequenz.client.common.microgrid import MicrogridId
from frequenz.client.common.microgrid.electrical_components import ElectricalComponentId
from frequenz.microgrid_component_graph import ComponentGraph, ComponentGraphConfig

_logger = logging.getLogger(__name__)

MicrogridComponentGraph = ComponentGraph[
    ElectricalComponent, ComponentConnection, ElectricalComponentId
]
"""Component graph specialized for a microgrid's electrical components."""


class ComponentGraphGenerator:
    """Generates component graphs for microgrids using the Assets API."""

    def __init__(
        self,
        client: AssetsApiClient,
        config: ComponentGraphConfig | None = None,
    ) -> None:
        """Initialize this instance.

        Args:
            client: The Assets API client to use for fetching components and
                connections.
            config: How to build the graph and generate its formulas. See
                `ComponentGraphConfig`. Defaults to that class's own defaults.
        """
        self._client: AssetsApiClient = client
        self._config: ComponentGraphConfig = (
            config if config is not None else ComponentGraphConfig()
        )

    async def get_component_graph(
        self, microgrid_id: MicrogridId
    ) -> MicrogridComponentGraph:
        """Generate a component graph for the given microgrid ID.

        Args:
            microgrid_id: The ID of the microgrid to generate the graph for.

        Returns:
            The component graph representing the microgrid's electrical
                components and their connections.

        Raises:
            ValueError: If any component connections could not be loaded.
        """
        components = await self._client.list_microgrid_electrical_components(
            microgrid_id
        )
        connections = (
            await self._client.list_microgrid_electrical_component_connections(
                microgrid_id
            )
        )

        if any(c is None for c in connections):
            raise ValueError("Failed to load all electrical component connections.")

        breakers = [c for c in components if isinstance(c, Breaker)]
        connected_breakers = [
            b
            for b in breakers
            if any(
                b.id in (c.source, c.destination) for c in connections if c is not None
            )
        ]

        if connected_breakers:
            _logger.warning(
                "The following breakers are connected to other components, "
                + "which is not supported by the component graph generator and may "
                + "lead to graph traversal issues: %s",
                [b.id for b in connected_breakers],
            )
        elif breakers:
            _logger.debug("Dropping unconnected breakers: %s", [b.id for b in breakers])
            components = [c for c in components if not isinstance(c, Breaker)]

        graph = ComponentGraph[
            ElectricalComponent, ComponentConnection, ElectricalComponentId
        ](components, connections, self._config)

        return graph


def _ids_of(
    graph: MicrogridComponentGraph, component_class: type[ElectricalComponent]
) -> list[int]:
    """Return the sorted IDs of all components of the given class."""
    return sorted(int(c.id) for c in graph.components(matching_types=component_class))


def _meter_ids_where(
    graph: MicrogridComponentGraph,
    is_meter: Callable[[ElectricalComponentId], bool],
) -> list[int]:
    """Return the sorted IDs of all meters matching the given classifier."""
    return sorted(
        int(m.id) for m in graph.components(matching_types=Meter) if is_meter(m.id)
    )


def grid_meter_ids(graph: MicrogridComponentGraph) -> list[int]:
    """Return the meters directly downstream of a grid connection point.

    Grid meters have no dedicated classifier, so they are derived from the graph
    topology.
    """
    grid_ids = {int(c.id) for c in graph.components(matching_types=GridConnectionPoint)}
    return sorted(
        int(m.id)
        for m in graph.components(matching_types=Meter)
        if any(int(p.id) in grid_ids for p in graph.predecessors(m.id))
    )


def pv_meter_ids(graph: MicrogridComponentGraph) -> list[int]:
    """Return the sorted IDs of all PV meters."""
    return _meter_ids_where(graph, graph.is_pv_meter)


def pv_inverter_ids(graph: MicrogridComponentGraph) -> list[int]:
    """Return the sorted IDs of all solar inverters."""
    return _ids_of(graph, SolarInverter)


def battery_meter_ids(graph: MicrogridComponentGraph) -> list[int]:
    """Return the sorted IDs of all battery meters."""
    return _meter_ids_where(graph, graph.is_battery_meter)


def battery_inverter_ids(graph: MicrogridComponentGraph) -> list[int]:
    """Return the sorted IDs of all battery inverters."""
    return _ids_of(graph, BatteryInverter)


def battery_ids(graph: MicrogridComponentGraph) -> list[int]:
    """Return the sorted IDs of all batteries."""
    return _ids_of(graph, Battery)


def battery_units(graph: MicrogridComponentGraph) -> dict[int, list[int]]:
    """Return the batteries wired to each battery inverter.

    The result maps every battery inverter ID to the sorted IDs of the
    batteries downstream of it, keyed in ascending inverter ID order. An
    inverter with no battery maps to an empty list, so a wiring problem
    stays visible to the caller.
    """
    units: dict[int, list[int]] = {}
    for inverter in graph.components(matching_types=BatteryInverter):
        batteries: set[int] = set()
        seen: set[int] = set()
        queue = [inverter.id]
        while queue:
            for successor in graph.successors(queue.pop()):
                if int(successor.id) in seen:
                    continue
                seen.add(int(successor.id))
                if isinstance(successor, Battery):
                    batteries.add(int(successor.id))
                else:
                    queue.append(successor.id)
        units[int(inverter.id)] = sorted(batteries)
    return dict(sorted(units.items()))


def chp_meter_ids(graph: MicrogridComponentGraph) -> list[int]:
    """Return the sorted IDs of all CHP meters."""
    return _meter_ids_where(graph, graph.is_chp_meter)


def chp_ids(graph: MicrogridComponentGraph) -> list[int]:
    """Return the sorted IDs of all CHPs."""
    return _ids_of(graph, Chp)


def ev_charger_meter_ids(graph: MicrogridComponentGraph) -> list[int]:
    """Return the sorted IDs of all EV charger meters."""
    return _meter_ids_where(graph, graph.is_ev_charger_meter)


def ev_charger_ids(graph: MicrogridComponentGraph) -> list[int]:
    """Return the sorted IDs of all EV chargers."""
    return _ids_of(graph, EvCharger)
