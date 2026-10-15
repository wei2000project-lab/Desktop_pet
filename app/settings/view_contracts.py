"""Temporary compatibility exports; canonical definitions live in contracts.

Remove this import bridge during phase-six cleanup. No duplicate classes live
here, so close-choice identity remains stable during the migration.
"""
from app.contracts.settings import CloseChoice, CloseRequest, ConnectionInputs, TestTarget

__all__ = ["CloseChoice", "CloseRequest", "ConnectionInputs", "TestTarget"]
