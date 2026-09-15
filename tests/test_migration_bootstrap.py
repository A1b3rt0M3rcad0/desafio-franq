from packages.core.migrations.bootstrap import SchemaState, classify_schema


def test_empty_database_is_migrated_normally() -> None:
    expected = {"agent_sessions": {"id", "created_at"}}
    inspection = classify_schema({}, expected)
    assert inspection.state == SchemaState.EMPTY


def test_versioned_database_is_always_handled_by_alembic() -> None:
    expected = {"agent_sessions": {"id"}}
    inspection = classify_schema(
        {"alembic_version": {"version_num"}, "agent_sessions": {"id"}},
        expected,
    )
    assert inspection.state == SchemaState.VERSIONED


def test_complete_legacy_schema_can_be_stamped_without_data_loss() -> None:
    expected = {
        "agent_sessions": {"id", "created_at"},
        "agent_executions": {"id", "session_id"},
    }
    inspection = classify_schema(
        {
            "agent_sessions": {"id", "created_at", "extra_legacy_column"},
            "agent_executions": {"id", "session_id"},
        },
        expected,
    )
    assert inspection.state == SchemaState.LEGACY_COMPATIBLE


def test_partial_legacy_schema_fails_instead_of_being_silently_stamped() -> None:
    expected = {
        "agent_sessions": {"id", "created_at"},
        "agent_executions": {"id", "session_id"},
    }
    inspection = classify_schema(
        {"agent_sessions": {"id"}},
        expected,
    )
    assert inspection.state == SchemaState.LEGACY_INCOMPATIBLE
    assert inspection.missing_tables == ("agent_executions",)
    assert inspection.missing_columns == ("agent_sessions.created_at",)
