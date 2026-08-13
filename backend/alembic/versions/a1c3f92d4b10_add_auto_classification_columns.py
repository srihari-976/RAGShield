"""add auto-classification columns to documents

Revision ID: a1c3f92d4b10
Revises: b7f424029549
Create Date: 2026-08-11 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c3f92d4b10'
down_revision: Union[str, None] = 'b7f424029549'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('classification_source', sa.String(length=20), nullable=False, server_default='manual'))
    op.add_column('documents', sa.Column('classifier_confidence', sa.Float(), nullable=True))
    op.add_column('documents', sa.Column('needs_review', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('documents', 'needs_review')
    op.drop_column('documents', 'classifier_confidence')
    op.drop_column('documents', 'classification_source')