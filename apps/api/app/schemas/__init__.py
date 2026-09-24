"""Pydantic v2 schemas for PlanGuard API."""
from app.schemas.workspaces import (
    WorkspaceCreate,
    WorkspaceUpdate,
    WorkspaceOut,
    ConnectionCreate,
    ConnectionUpdate,
    ConnectionOut,
    ConnectionTestResult,
    CapabilityCheck,
    JobOut,
    ErrorOut,
)
from app.schemas.workload import (
    WorkloadSnapshotOut,
    QueryFingerprintOut,
    QueryObservationOut,
    IndexCandidateOut,
    PlanSnapshotOut,
)
from app.schemas.experiments import (
    ExperimentCreate,
    ExperimentOut,
)
from app.schemas.recommendations import (
    RecommendationOut,
    MigrationArtifactOut,
)
from app.schemas.indexes import (
    IndexRecordOut,
)

__all__ = [
    "WorkspaceCreate",
    "WorkspaceUpdate",
    "WorkspaceOut",
    "ConnectionCreate",
    "ConnectionUpdate",
    "ConnectionOut",
    "ConnectionTestResult",
    "CapabilityCheck",
    "JobOut",
    "ErrorOut",
    "WorkloadSnapshotOut",
    "QueryFingerprintOut",
    "QueryObservationOut",
    "IndexCandidateOut",
    "PlanSnapshotOut",
    "ExperimentCreate",
    "ExperimentOut",
    "RecommendationOut",
    "MigrationArtifactOut",
    "IndexRecordOut",
]
