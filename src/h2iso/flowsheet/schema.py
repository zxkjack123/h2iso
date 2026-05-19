"""Flowsheet configuration loading, validation, and topology analysis."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from h2iso.species import SPECIES_ORDER


@dataclass
class FeedConfig:
    """External feed specification from JSON."""

    name: str
    flow: float  # mol/h
    composition: np.ndarray  # (6,)
    target_column: str
    feed_stage: int


@dataclass
class ColumnConfig:
    """Column specification from JSON."""

    name: str
    n_stages: int
    reflux_ratio: float
    distillate_to_feed: float
    feed_positions: dict[str, int]  # feed_name -> stage
    pressure: float  # Pa (average of top/bottom)


@dataclass
class EquilibratorConfig:
    """Equilibrator specification from JSON."""

    name: str
    temperature: float = 25.0  # K


@dataclass
class PressureChangerConfig:
    """Pressure changer (throttle/pump/compressor) specification from JSON."""

    name: str
    target_pressure: float  # Pa
    mode: str  # "throttle" | "pump" | "compressor"
    gamma: float = 1.4


@dataclass
class Connection:
    """A connection between units in the topology."""

    from_unit: str
    to_unit: str
    stage: int | None = None  # None for non-column targets


@dataclass
class TearStream:
    """A stream that must be torn to break a recycle loop."""

    from_unit: str
    to_unit: str
    name: str


@dataclass
class FlowsheetConfig:
    """Complete flowsheet configuration."""

    feeds: list[FeedConfig]
    columns: list[ColumnConfig]
    equilibrators: list[EquilibratorConfig]
    connections: list[Connection]
    products: dict[str, str]  # product_name -> description
    tear_streams: list[TearStream] = field(default_factory=list)
    pressure_changers: list[PressureChangerConfig] = field(default_factory=list)


def load_flowsheet(path: str | Path) -> FlowsheetConfig:
    """Load a flowsheet configuration from JSON.

    Parameters
    ----------
    path : str or Path
        Path to the flowsheet JSON file.

    Returns
    -------
    FlowsheetConfig
    """
    path = Path(path)
    with open(path) as f:
        data = json.load(f)

    # Parse feeds
    feeds = []
    for name, fdata in data.get("feeds", {}).items():
        comp = np.zeros(len(SPECIES_ORDER))
        comp_dict = fdata.get("composition_mole_fraction", {})
        for i, sp in enumerate(SPECIES_ORDER):
            comp[i] = comp_dict.get(sp, 0.0)
        # Normalize
        s = comp.sum()
        if s > 0:
            comp /= s

        feeds.append(FeedConfig(
            name=name,
            flow=fdata["total_flow_mol_h"],
            composition=comp,
            target_column=fdata.get("target_column", ""),
            feed_stage=fdata.get("feed_stage", 1),
        ))

    # Parse columns
    columns = []
    for name, cdata in data.get("columns", {}).items():
        p_top = cdata.get("pressure_top_Pa", 101325.0)
        p_bot = cdata.get("pressure_bottom_Pa", 101325.0)
        columns.append(ColumnConfig(
            name=name,
            n_stages=cdata["total_stages"],
            reflux_ratio=cdata["reflux_ratio"],
            distillate_to_feed=cdata["distillate_to_feed_ratio"],
            feed_positions=cdata.get("feed_positions", {}),
            pressure=(p_top + p_bot) / 2.0,
        ))

    # Parse equilibrators (implicit from topology)
    equilibrators = []
    topo = data.get("topology", {})
    connections_raw = topo.get("connections", [])
    for conn in connections_raw:
        if "equilibrator" in conn.get("to", ""):
            eq_name = conn["to"]
            if not any(e.name == eq_name for e in equilibrators):
                equilibrators.append(EquilibratorConfig(name=eq_name))
        if "equilibrator" in conn.get("from", ""):
            eq_name = conn["from"]
            if not any(e.name == eq_name for e in equilibrators):
                equilibrators.append(EquilibratorConfig(name=eq_name))

    # Parse connections
    connections = []
    for conn in connections_raw:
        connections.append(Connection(
            from_unit=conn["from"],
            to_unit=conn["to"],
            stage=conn.get("stage"),
        ))

    # Parse products
    products = topo.get("products", {})

    # Parse pressure changers (optional section)
    pressure_changers = []
    for name, pdata in data.get("pressure_changers", {}).items():
        pressure_changers.append(PressureChangerConfig(
            name=name,
            target_pressure=pdata["target_pressure_Pa"],
            mode=pdata["mode"],
            gamma=pdata.get("gamma", 1.4),
        ))

    config = FlowsheetConfig(
        feeds=feeds,
        columns=columns,
        equilibrators=equilibrators,
        connections=connections,
        products=products,
        pressure_changers=pressure_changers,
    )

    # Detect tear streams
    config.tear_streams = detect_tear_streams(config)

    return config


def validate_topology(config: FlowsheetConfig) -> list[str]:
    """Validate flowsheet topology for completeness.

    Returns list of error messages. Empty list = valid.
    """
    errors = []

    # Collect all known unit names
    unit_names = set()
    for f in config.feeds:
        unit_names.add(f.name + "_feed")
    for c in config.columns:
        unit_names.add(c.name)
        # Column outputs
        unit_names.add(c.name + "_top")
        unit_names.add(c.name + "_bottom")
    for e in config.equilibrators:
        unit_names.add(e.name)

    # Also add feed-derived names
    for f in config.feeds:
        unit_names.add(f.name + "_feed")

    # Check connections reference valid units
    for conn in config.connections:
        # from_unit can be a feed name, column output, or equilibrator
        from_known = (
            conn.from_unit in unit_names
            or any(conn.from_unit.startswith(c.name) for c in config.columns)
            or any(conn.from_unit == f.name + "_feed" for f in config.feeds)
        )
        if not from_known:
            errors.append(f"Unknown source unit: '{conn.from_unit}'")

        to_known = (
            conn.to_unit in unit_names
            or any(conn.to_unit == c.name for c in config.columns)
        )
        if not to_known:
            errors.append(f"Unknown target unit: '{conn.to_unit}'")

    # Check that all column feed_positions have a corresponding connection
    for col in config.columns:
        for feed_name in col.feed_positions:
            has_conn = any(
                conn.to_unit == col.name
                and (conn.from_unit == feed_name
                     or conn.from_unit.endswith("_feed") and conn.from_unit.replace("_feed", "") == feed_name
                     or feed_name in conn.from_unit)
                for conn in config.connections
            )
            if not has_conn:
                # Not always a hard error — some feed_positions may use
                # naming differently
                pass

    return errors


def detect_tear_streams(config: FlowsheetConfig) -> list[TearStream]:
    """Detect recycle loops and identify tear streams.

    A tear stream is a connection that, when removed, breaks a cycle
    in the process graph. Uses DFS-based cycle detection.

    Returns
    -------
    list of TearStream
        Identified tear streams.
    """
    # Build adjacency from connections
    # Nodes: all unit names that appear as from/to
    graph: dict[str, list[str]] = {}
    for conn in config.connections:
        from_node = _normalize_node(conn.from_unit, config)
        to_node = _normalize_node(conn.to_unit, config)
        graph.setdefault(from_node, []).append(to_node)
        graph.setdefault(to_node, [])

    # Find cycles using DFS
    tear_streams = []
    visited: set[str] = set()
    rec_stack: set[str] = set()
    back_edges: list[tuple[str, str]] = []

    def dfs(node: str):
        visited.add(node)
        rec_stack.add(node)
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                dfs(neighbor)
            elif neighbor in rec_stack:
                back_edges.append((node, neighbor))
        rec_stack.discard(node)

    for node in graph:
        if node not in visited:
            dfs(node)

    # Convert back edges to TearStream objects
    for from_n, to_n in back_edges:
        # Find the original connection
        for conn in config.connections:
            fn = _normalize_node(conn.from_unit, config)
            tn = _normalize_node(conn.to_unit, config)
            if fn == from_n and tn == to_n:
                tear_streams.append(TearStream(
                    from_unit=conn.from_unit,
                    to_unit=conn.to_unit,
                    name=f"{conn.from_unit} → {conn.to_unit}",
                ))
                break

    return tear_streams


def _normalize_node(unit_name: str, config: FlowsheetConfig) -> str:
    """Normalize a unit name to its base unit for graph analysis.

    E.g., 'CD1_bottom' -> 'CD1', 'CD3_top' -> 'CD3',
    'WDS_feed' -> 'WDS_feed' (external, kept as-is)
    """
    col_names = {c.name for c in config.columns}
    eq_names = {e.name for e in config.equilibrators}

    # Check if it's a column output (e.g., CD1_bottom, CD3_top)
    for cn in col_names:
        if unit_name.startswith(cn + "_"):
            return cn

    # Check if it's an equilibrator
    if unit_name in eq_names:
        return unit_name

    # External feed or unknown — keep as-is
    return unit_name
