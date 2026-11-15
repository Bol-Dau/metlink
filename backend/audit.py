import json
from typing import Any


def _to_json_text(value: Any) -> str | None:
    """Convert a dictionary or value into a clean JSON string for audit storage."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str)


def log_admin_action(
    cur,
    admin_id: int,
    action: str,
    entity: str,
    record_id: int,
    details: str,
    old_value: Any = None,
    new_value: Any = None,
) -> None:
    """
    Record an admin change inside the current database transaction.

    Example actions: 'CREATE', 'UPDATE', 'DEACTIVATE', 'ACTIVATE'
    Example entities: 'farmers', 'market_information', 'seasonal_information', 'decision_rules'
    """
    cur.execute(
        """
        INSERT INTO audit_logs (
            admin_id, action, entity, record_id, old_value, new_value, details
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s);
        """,
        (
            admin_id,
            action.upper(),
            entity,
            record_id,
            _to_json_text(old_value),
            _to_json_text(new_value),
            details,
        ),
    )
