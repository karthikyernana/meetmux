"""Workspace and Connection API router."""
from __future__ import annotations

import uuid
from typing import Any

import psycopg
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_db
from app.domains.experiments.models import Recommendation
from app.domains.workload.models import WorkloadSnapshot
from app.domains.workspaces.models import Connection, Workspace
from app.schemas.workspaces import (
    CapabilityCheck,
    ConnectionCreate,
    ConnectionOut,
    ConnectionTestResult,
    ConnectionUpdate,
    WorkspaceCreate,
    WorkspaceOut,
    WorkspaceUpdate,
)
from app.security.credentials import decrypt_credential, encrypt_credential

logger = get_logger(__name__)
router = APIRouter(prefix="/workspaces", tags=["workspaces"])


async def _enrich_workspace(db: AsyncSession, ws: Workspace) -> WorkspaceOut:
    conn = (await db.execute(select(Connection.id).where(Connection.workspace_id == ws.id))).scalar_one_or_none()
    conn_state = "connected" if conn else "disconnected"

    snap = (await db.execute(
        select(WorkloadSnapshot.captured_at)
        .where(WorkloadSnapshot.workspace_id == ws.id)
        .order_by(WorkloadSnapshot.captured_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    rec_count = (await db.execute(
        select(func.count(Recommendation.id))
        .where(
            Recommendation.workspace_id == ws.id,
            Recommendation.status.in_(["RECOMMENDED", "REVIEW_REQUIRED"]),
        )
    )).scalar_one() or 0

    return WorkspaceOut(
        id=ws.id,
        name=ws.name,
        environment_label=ws.environment_label,
        status=ws.status,
        created_at=ws.created_at,
        updated_at=ws.updated_at,
        connection_state=conn_state,
        last_snapshot_at=snap,
        open_recommendation_count=rec_count,
    )


# ── Workspace CRUD ────────────────────────────────────────────────────────────


@router.post("", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
async def create_workspace(body: WorkspaceCreate, db: AsyncSession = Depends(get_db)) -> WorkspaceOut:
    workspace = Workspace(name=body.name, environment_label=body.environment_label)
    db.add(workspace)
    await db.commit()
    await db.refresh(workspace)
    logger.info("workspace_created", workspace_id=str(workspace.id))
    return await _enrich_workspace(db, workspace)


@router.get("", response_model=list[WorkspaceOut])
@router.get("/", response_model=list[WorkspaceOut])
async def list_workspaces(db: AsyncSession = Depends(get_db)) -> list[WorkspaceOut]:
    result = await db.execute(select(Workspace).order_by(Workspace.created_at.desc()))
    workspaces = list(result.scalars().all())
    return [await _enrich_workspace(db, ws) for ws in workspaces]


@router.get("/{workspace_id}", response_model=WorkspaceOut)
async def get_workspace(workspace_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> WorkspaceOut:
    ws = await _get_or_404(db, workspace_id)
    return await _enrich_workspace(db, ws)


@router.patch("/{workspace_id}", response_model=WorkspaceOut)
async def update_workspace(
    workspace_id: uuid.UUID, body: WorkspaceUpdate, db: AsyncSession = Depends(get_db)
) -> WorkspaceOut:
    ws = await _get_or_404(db, workspace_id)
    if body.name is not None:
        ws.name = body.name
    if body.environment_label is not None:
        ws.environment_label = body.environment_label
    await db.commit()
    await db.refresh(ws)
    return await _enrich_workspace(db, ws)


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(workspace_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    ws = await _get_or_404(db, workspace_id)
    await db.delete(ws)
    await db.commit()


# ── Connection ────────────────────────────────────────────────────────────────


@router.post("/{workspace_id}/connection/test", response_model=ConnectionTestResult)
async def test_connection(workspace_id: uuid.UUID, body: ConnectionCreate) -> ConnectionTestResult:
    """Dial the target PostgreSQL and run capability checks. Does NOT persist credentials."""
    return await _run_capability_check(body)


@router.post("/{workspace_id}/connection", response_model=ConnectionOut, status_code=status.HTTP_201_CREATED)
@router.put("/{workspace_id}/connection", response_model=ConnectionOut, status_code=status.HTTP_200_OK)
async def save_connection(
    workspace_id: uuid.UUID, body: ConnectionCreate, db: AsyncSession = Depends(get_db)
) -> Connection:
    await _get_or_404(db, workspace_id)
    encrypted = encrypt_credential(body.password)
    test_result = await _run_capability_check(body)

    # Upsert
    result = await db.execute(
        select(Connection).where(Connection.workspace_id == workspace_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        conn = existing
    else:
        conn = Connection(workspace_id=workspace_id)
        db.add(conn)

    conn.host = body.host
    conn.port = body.port
    conn.database_name = body.database_name
    conn.username = body.username
    conn.credential_reference = encrypted
    conn.ssl_mode = body.ssl_mode
    conn.server_version = test_result.server_version
    conn.capability_status = {c.name: {"status": c.status, "detail": c.detail} for c in test_result.capabilities}

    await db.commit()
    await db.refresh(conn)
    logger.info("connection_saved", workspace_id=str(workspace_id))
    return conn


@router.get("/{workspace_id}/connection/status", response_model=ConnectionOut)
async def get_connection_status(workspace_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Connection:
    result = await db.execute(
        select(Connection).where(Connection.workspace_id == workspace_id)
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="No connection configured for this workspace")
    return conn


@router.patch("/{workspace_id}/connection", response_model=ConnectionOut)
async def update_connection(
    workspace_id: uuid.UUID, body: ConnectionUpdate, db: AsyncSession = Depends(get_db)
) -> Connection:
    result = await db.execute(
        select(Connection).where(Connection.workspace_id == workspace_id)
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="No connection configured for this workspace")

    if body.host is not None:
        conn.host = body.host
    if body.port is not None:
        conn.port = body.port
    if body.database_name is not None:
        conn.database_name = body.database_name
    if body.username is not None:
        conn.username = body.username
    if body.password is not None:
        conn.credential_reference = encrypt_credential(body.password)
    if body.ssl_mode is not None:
        conn.ssl_mode = body.ssl_mode

    await db.commit()
    await db.refresh(conn)
    return conn


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_or_404(db: AsyncSession, workspace_id: uuid.UUID) -> Workspace:
    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


async def _run_capability_check(body: ConnectionCreate) -> ConnectionTestResult:
    """Connect to target PostgreSQL and probe capabilities."""
    checks: list[CapabilityCheck] = []
    server_version: str | None = None

    try:
        conn_params = {
            "host": body.host,
            "port": body.port,
            "dbname": body.database_name,
            "user": body.username,
            "password": body.password,
            "sslmode": body.ssl_mode or "prefer",
            "connect_timeout": 10,
        }
        async with await psycopg.AsyncConnection.connect(**conn_params) as aconn:
            # 1. Server version
            cur = await aconn.execute("SELECT version()")
            row = await cur.fetchone()
            if row:
                server_version = row[0]
                checks.append(CapabilityCheck(name="postgresql_connectivity", status="ok", detail=server_version))

            # 2. pg_stat_statements
            try:
                cur = await aconn.execute(
                    "SELECT count(*) FROM pg_extension WHERE extname = 'pg_stat_statements'"
                )
                row = await cur.fetchone()
                if row and row[0] > 0:
                    checks.append(CapabilityCheck(name="pg_stat_statements_enabled", status="ok"))
                else:
                    checks.append(CapabilityCheck(name="pg_stat_statements_enabled", status="warning", detail="Extension not installed in database"))
            except Exception as e:
                checks.append(CapabilityCheck(name="pg_stat_statements_enabled", status="failed", detail=str(e)))

            # 3. Query text access
            try:
                await aconn.execute("SELECT query FROM pg_stat_statements LIMIT 1")
                checks.append(CapabilityCheck(name="query_text_access", status="ok"))
            except Exception as e:
                checks.append(CapabilityCheck(name="query_text_access", status="warning", detail=str(e)))

            # 4. Schema metadata
            try:
                await aconn.execute("SELECT count(*) FROM information_schema.tables LIMIT 1")
                checks.append(CapabilityCheck(name="schema_metadata_access", status="ok"))
            except Exception as e:
                checks.append(CapabilityCheck(name="schema_metadata_access", status="failed", detail=str(e)))

            # 5. Statistics access
            try:
                await aconn.execute("SELECT count(*) FROM pg_stat_user_tables LIMIT 1")
                checks.append(CapabilityCheck(name="statistics_access", status="ok"))
            except Exception as e:
                checks.append(CapabilityCheck(name="statistics_access", status="failed", detail=str(e)))

            # 6. HypoPG
            try:
                cur = await aconn.execute(
                    "SELECT count(*) FROM pg_extension WHERE extname = 'hypopg'"
                )
                row = await cur.fetchone()
                if row and row[0] > 0:
                    checks.append(CapabilityCheck(name="hypopg_available", status="ok"))
                else:
                    checks.append(CapabilityCheck(name="hypopg_available", status="warning", detail="HypoPG not installed — fallback simulation active"))
            except Exception as e:
                checks.append(CapabilityCheck(name="hypopg_available", status="warning", detail=str(e)))

        return ConnectionTestResult(success=True, server_version=server_version, capabilities=checks)

    except Exception as exc:
        logger.warning("connection_test_failed", error=str(exc))
        return ConnectionTestResult(
            success=False,
            error=str(exc),
            capabilities=checks,
        )
