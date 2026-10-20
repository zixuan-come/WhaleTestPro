"""Explicit ORM registration shared by standalone operational entry points."""
from importlib import import_module


def register_models():
    # A physical FK target in an existing database is not enough: SQLAlchemy
    # also needs every referenced table and relationship in this process's
    # metadata before a migration creates a new dependent table.
    for name in (
        "user", "team", "team_member", "team_invitation", "team_permission",
        "project", "project_notification", "environment", "interface", "case",
        "scenario", "suite", "schedule", "schedule_sync_outbox", "report",
        "execution_report", "scenario_report", "report_folder", "perf", "mock",
        "traffic_record", "traffic_capture", "demo_order",
    ):
        import_module(f"app.models.{name}")
