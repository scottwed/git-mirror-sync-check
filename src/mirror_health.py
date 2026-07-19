from datetime import datetime, timezone
from enum import Enum
from ipaddress import IPv4Address, IPv6Address
from typing import Annotated, Iterable, Optional, Union

from pydantic import BaseModel, Field, field_validator
import requests


IPAddress = Union[IPv4Address, IPv6Address]

METRIC_PREFIX = "git_mirror"


class MirrorRole(str, Enum):
    primary = "primary"
    secondary = "secondary"
    tertiary = "tertiary"


class GitMirrorHealth(BaseModel):
    """Availability and sync-health metrics for a single mirrored repo on a single mirror server."""

    # Identity
    project: Annotated[str, Field(frozen=True, description="Repo/project identifier, e.g. 'org/repo'")]
    mirror_host: Annotated[str, Field(frozen=True, description="Hostname or ID of the mirror server")]
    ip_address: Annotated[IPAddress, Field(frozen=True, description="IP address of the mirror server")]
    role: Annotated[MirrorRole, Field(frozen=True, description="Mirror's role: primary/secondary/tertiary")]

    # Availability (0/1, Prometheus-style gauges) ---
    up: Annotated[
        int, Field(ge=0, le=1, description="Whether the mirror host/service is reachable")
    ] = 0
    in_service: Annotated[
        int, Field(ge=0, le=1, description="Whether the mirror is actively serving traffic")
    ] = 1

    # Sync health
    in_sync: Annotated[
        int, Field(ge=0, le=1, description="Whether the mirror is currently in sync with source")
    ] = 0
    last_in_sync: Annotated[
        Optional[datetime],
        Field(description="UTC timestamp of the last confirmed in-sync state"),
    ] = None
    sync_errors_total: Annotated[
        int, Field(ge=0, description="Cumulative count of sync errors")
    ] = 0
    last_error_message: Annotated[
         str, Field(description="Most recent sync error message, if any")
    ] = ""

    # Metadata
    index_snapshot: Annotated[
        str,
        Field(description="Snapshot of the last successfully retrieved index."),
    ] = ""

    model_config = {"use_enum_values": True}

    @field_validator("last_in_sync")
    @classmethod
    def _ensure_utc(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is not None and v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v

    # Prometheus export

    def _base_labels(self) -> dict:
        return {
            "project": self.project,
            "mirror_host": self.mirror_host,
            "role": self.role,
            "ip_address": str(self.ip_address),
        }

    def to_prometheus_samples(self) -> str:
        """Render this instance's metrics as Prometheus exposition-format
        sample lines (no HELP/TYPE headers -- use `render_prometheus()`
        for a full multi-instance document with headers)."""
        labels = self._base_labels()
        lines = [
            _sample(f"{METRIC_PREFIX}_up", labels, self.up),
            _sample(f"{METRIC_PREFIX}_in_service", labels, self.in_service),
            _sample(f"{METRIC_PREFIX}_in_sync", labels, self.in_sync),
            _sample(f"{METRIC_PREFIX}_sync_errors_total", labels, self.sync_errors_total),
        ]
        if self.last_in_sync is not None:
            lines.append(
                _sample(
                    f"{METRIC_PREFIX}_last_sync_timestamp_seconds",
                    labels,
                    int(self.last_in_sync.timestamp()),
                )
            )
        if self.last_error_message:
            error_labels = {**labels, "error": self.last_error_message}
            lines.append(_sample(f"{METRIC_PREFIX}_last_error_info", error_labels, 1))
        return "\n".join(lines)


def _escape_label_value(value: str) -> str:
    # Prometheus label-value escaping: backslash, double-quote, newline.
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
    )


def _sample(metric: str, labels: dict, value) -> str:
    label_str = ",".join(f'{k}="{_escape_label_value(str(v))}"' for k, v in labels.items())
    return f"{metric}{{{label_str}}} {value}"


# HELP/TYPE metadata, emitted once per metric name regardless of how many
# instances are rendered together.
_METRIC_METADATA = [
    (f"{METRIC_PREFIX}_up", "gauge", "Whether the mirror host/service is reachable (1=up, 0=down)"),
    (f"{METRIC_PREFIX}_in_service", "gauge", "Whether the mirror is actively serving traffic (1=yes, 0=no)"),
    (f"{METRIC_PREFIX}_in_sync", "gauge", "Whether the mirror is currently in sync with its source (1=yes, 0=no)"),
    (f"{METRIC_PREFIX}_sync_errors_total", "counter", "Cumulative count of sync errors"),
    (f"{METRIC_PREFIX}_last_sync_timestamp_seconds", "gauge", "Unix timestamp of the last confirmed in-sync state"),
    (f"{METRIC_PREFIX}_last_error_info", "gauge", "Info metric carrying the last sync error message as a label"),
]


def render_prometheus(metrics: Iterable[GitMirrorHealth]) -> str:
    """Render a full Prometheus exposition-format document for multiple
    GitMirrorHealth instances, with HELP/TYPE headers emitted once per
    metric name. This is the payload you'd write to a textfile-collector
    path, or POST as the body to VictoriaMetrics'
    /api/v1/import/prometheus endpoint."""
    metrics = list(metrics)
    blocks = []
    for name, mtype, help_text in _METRIC_METADATA:
        samples = []
        for m in metrics:
            for line in m.to_prometheus_samples().splitlines():
                if line.startswith(name + "{"):
                    samples.append(line)
        if not samples:
            continue
        block = [f"# HELP {name} {help_text}", f"# TYPE {name} {mtype}", *samples]
        blocks.append("\n".join(block))
    return "\n".join(blocks) + "\n"


def push_to_victoria_metrics(metrics: Iterable[GitMirrorHealth], url: str, timeout: float = 5.0) -> None:
    """Push metrics directly to VictoriaMetrics via its Prometheus
    exposition-format import endpoint, e.g.:
        push_to_victoriametrics(metrics, "http://vm:8428/api/v1/import/prometheus")
    Requires the `requests` package.
    """

    payload = render_prometheus(metrics)
    resp = requests.post(url, data=payload.encode("utf-8"), timeout=timeout)
    resp.raise_for_status()