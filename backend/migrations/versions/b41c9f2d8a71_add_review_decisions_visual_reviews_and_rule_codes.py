"""Add review decisions, visual reviews and deterministic rule codes.

Revision ID: b41c9f2d8a71
Revises: 72f033062d6e
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "b41c9f2d8a71"
down_revision: Union[str, Sequence[str], None] = "72f033062d6e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("brand_rules", sa.Column("rule_code", sa.String(length=20), nullable=True))

    op.create_table(
        "review_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("finding_index", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("replacement_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["review_id"], ["content_reviews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("review_id", "finding_index", name="uq_review_finding_decision"),
    )
    op.create_index("ix_review_decisions_review_id", "review_decisions", ["review_id"], unique=False)

    op.create_table(
        "visual_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("brand_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_visual_reviews_brand_id", "visual_reviews", ["brand_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_visual_reviews_brand_id", table_name="visual_reviews")
    op.drop_table("visual_reviews")
    op.drop_index("ix_review_decisions_review_id", table_name="review_decisions")
    op.drop_table("review_decisions")
    op.drop_column("brand_rules", "rule_code")
