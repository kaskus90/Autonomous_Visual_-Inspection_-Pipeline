"""initial schema

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "detections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("frame_id", sa.String(64), nullable=False),
        sa.Column("line_id", sa.String(64), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("class_name", sa.String(128), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("bbox", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_detections_line_id", "detections", ["line_id"])
    op.create_index("ix_detections_timestamp", "detections", ["timestamp"])
    op.create_index("ix_detections_class_name", "detections", ["class_name"])

    op.create_table(
        "alert_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("line_id", sa.String(64), nullable=False),
        sa.Column("defect_rate_threshold", sa.Integer(), default=5),
        sa.Column("window_seconds", sa.Integer(), default=60),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("line_id"),
    )

    op.create_table(
        "alert_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("line_id", sa.String(64), nullable=False),
        sa.Column("defect_count", sa.Integer(), nullable=False),
        sa.Column("threshold", sa.Integer(), nullable=False),
        sa.Column("fired_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_logs_line_id", "alert_logs", ["line_id"])


def downgrade() -> None:
    op.drop_table("alert_logs")
    op.drop_table("alert_configs")
    op.drop_table("detections")
