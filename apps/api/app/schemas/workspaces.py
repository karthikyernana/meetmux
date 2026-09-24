"""
Pydantic v2 schemas for Workspaces and Connections API.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Workspace ─────────────────────────────────────────────────────────────────

class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    environment_label: str = Field(default="production", max_length=100)


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    environment_label: str | None = Field(default=None, max_length=100)


class WorkspaceOut(BaseModel):
    id: uuid.UUID
    name: str
    environment_label: str
    status: str
    created_at: datetime
    updated_at: datetime
    # Derived summary fields (joined at query time)
    connection_state: str | None = None
    last_snapshot_at: datetime | None = None
    open_recommendation_count: int = 0

    model_config = {"from_attributes": True}


# ── Connection ────────────────────────────────────────────────────────────────

class ConnectionCreate(BaseModel):
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(default=5432, ge=1, le=65535)
    database_name: str = Field(..., min_length=1, max_length=255)
    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, description="Stored encrypted, never returned")
    ssl_mode: str = Field(default="prefer", pattern="^(disable|allow|prefer|require|verify-ca|verify-full)$")


class ConnectionUpdate(BaseModel):
    host: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    database_name: str | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = None
    ssl_mode: str | None = Field(
        default=None, pattern="^(disable|allow|prefer|require|verify-ca|verify-full)$"
    )


class CapabilityCheck(BaseModel):
    name: str
    status: str  # ok | warning | failed
    detail: str | None = None


class ConnectionTestResult(BaseModel):
    success: bool
    server_version: str | None = None
    capabilities: list[CapabilityCheck] = []
    error: str | None = None


class ConnectionOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    host: str
    port: int
    database_name: str
    username: str
    ssl_mode: str
    server_version: str | None
    capability_status: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Jobs ──────────────────────────────────────────────────────────────────────

class JobOut(BaseModel):
    job_id: str
    status: str
    created_at: datetime | None = None


# ── Shared ────────────────────────────────────────────────────────────────────

class ErrorOut(BaseModel):
    error_code: str
    message: str
    detail: str | None = None
