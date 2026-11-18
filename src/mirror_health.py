from datetime import datetime, timezone
from enum import Enum
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Annotated, Optional, Union

from _socket import gethostbyname
from pydantic import BaseModel, Field, field_validator

IPAddress = Union[IPv4Address, IPv6Address]

METRIC_PREFIX = "git_mirror"


class MirrorRole(str, Enum):
    primary = "primary"
    mirror = "mirror"


# noinspection PyStringConversionWithoutDunderMethod
class GitMirrorHealth(BaseModel):
    """Availability and sync-health metrics for a project on one git server."""

    # Identity
    project: Annotated[str, Field(frozen=True, description="Repo/project identifier, e.g. 'org/repo'")]
    instance: Annotated[str, Field(frozen=True, description="Hostname or ID of the mirror server")]
    ip_address: Annotated[IPAddress, Field(frozen=True, description="IP address of the mirror server")]
    role: Annotated[MirrorRole, Field(frozen=True, description="Mirror's role: primary/secondary/tertiary")]

    # Availability (0/1, Prometheus-style gauges)
    up: Annotated[
        int, Field(ge=0, le=1, description="Whether the mirror host/service is reachable")
    ] = 0
    git_port_open: Annotated[
        int, Field(ge=0, le=1, description="Whether the git port TCP 9418 is responsive")
    ] = 0
    in_service: Annotated[
        int, Field(ge=0, le=1, description="Whether the mirror is actively serving traffic")
    ] = 1

    # Sync health
    in_sync: Annotated[
        int, Field(ge=0, le=1, description="Whether the mirror is currently in sync with the source")
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


def prepare_mirror_health_objects(
        repo_path: str, repos_for_project: dict[str, list[GitMirrorHealth]],
        primary_repo_fqdn: str, mirror_hosts: list[str]) -> None:
    # On-demand initialization of the mirror health instances.
    # First item in the list will be the primary, followed by all the mirrors.
    if repo_path not in repos_for_project:
        primary_repo_addr: str = gethostbyname(primary_repo_fqdn)
        primary_health = GitMirrorHealth(
            project=repo_path, instance=primary_repo_fqdn, ip_address=ip_address(primary_repo_addr),
            role=MirrorRole.primary, up=0, in_service=1, in_sync=1,
            last_in_sync=datetime.now(), sync_errors_total=0, last_error_message="",
            index_snapshot="")
        repos_for_project[repo_path] = [primary_health]

        # Create placeholders for all the mirrors
        for mirror in mirror_hosts:
            mh = GitMirrorHealth(
                project=repo_path, instance=mirror, ip_address=ip_address(mirror),
                role=MirrorRole.mirror, up=0, in_service=1, in_sync=0,
                last_in_sync=datetime.min, sync_errors_total=0, last_error_message="",
                index_snapshot="")
            repos_for_project[repo_path].append(mh)
