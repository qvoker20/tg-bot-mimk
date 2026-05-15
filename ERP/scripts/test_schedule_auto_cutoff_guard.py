from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
ERP_DIR = CURRENT_FILE.parents[1]
if str(ERP_DIR) not in sys.path:
    sys.path.insert(0, str(ERP_DIR))

from app.modules.assemblers.db.connection import get_db_connection
from app.modules.assemblers.services.registry.constants import (
    DETAIL_RECALC_QUEUE_TABLE,
    DETAILS_TABLE_NAME,
    MAIN_TABLE_NAME,
)
from app.modules.assemblers.services.schedule.constants import (
    SCHEDULE_TASKS_TABLE,
    TASK_STATUS_IN_PROGRESS,
)
from app.modules.assemblers.services.schedule.schema import ensure_schedule_schema


AUTO_CLOSE_RUNS_TABLE = "assemblers_schedule_auto_close_runs"


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_test() -> None:
    ensure_schedule_schema()

    test_day = date.today()
    test_order = f"TEST-AUTO-CUTOFF-{test_day.isoformat()}"
    test_part = "999"
    test_product = "AUTO CUTOFF TEST PRODUCT"

    with get_db_connection() as conn:
        try:
            with conn.cursor() as cursor:
                # Clean up potential leftovers from earlier runs with the same order number.
                cursor.execute(f"DELETE FROM {SCHEDULE_TASKS_TABLE} WHERE order_number = %s", (test_order,))
                cursor.execute(f"DELETE FROM {DETAILS_TABLE_NAME} WHERE order_number = %s", (test_order,))
                cursor.execute(f"DELETE FROM {MAIN_TABLE_NAME} WHERE order_number = %s", (test_order,))
                cursor.execute(f"DELETE FROM {DETAIL_RECALC_QUEUE_TABLE} WHERE order_number = %s", (test_order,))

                cursor.execute(
                    f"""
                    INSERT INTO {MAIN_TABLE_NAME} (order_number, customer, status)
                    VALUES (%s, %s, %s)
                    """,
                    (test_order, "TEST CUSTOMER", "Розподіл"),
                )

                cursor.execute(
                    f"""
                    INSERT INTO {DETAILS_TABLE_NAME} (
                        order_number,
                        part_number,
                        customer,
                        product_name,
                        requires_assembly,
                        requires_install,
                        assembly_status,
                        install_status
                    )
                    VALUES (%s, %s, %s, %s, TRUE, TRUE, '', '')
                    RETURNING id
                    """,
                    (test_order, test_part, "TEST CUSTOMER", test_product),
                )
                detail_id = int(cursor.fetchone()[0])

                cursor.execute(
                    f"""
                    INSERT INTO {SCHEDULE_TASKS_TABLE} (
                        source_user_id,
                        assembler_name,
                        subdivision,
                        scheduled_for,
                        task_type,
                        status,
                        order_number,
                        customer,
                        part_number,
                        product_name,
                        constructor_status,
                        description,
                        started_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW() - INTERVAL '3 hours')
                    RETURNING id
                    """,
                    (
                        9999991,
                        "TEST ASSEMBLER",
                        "private",
                        test_day,
                        "assembly",
                        TASK_STATUS_IN_PROGRESS,
                        test_order,
                        "TEST CUSTOMER",
                        test_part,
                        test_product,
                        "",
                        "test cutoff path",
                    ),
                )
                task_id = int(cursor.fetchone()[0])

                cursor.execute(
                    f"""
                    SELECT assembly_status, assembly_completed_at, install_status, install_completed_at
                    FROM {DETAILS_TABLE_NAME}
                    WHERE id = %s
                    """,
                    (detail_id,),
                )
                before_detail = cursor.fetchone()

                # Reset queue baseline to isolate only cutoff side effects.
                cursor.execute(
                    f"DELETE FROM {DETAIL_RECALC_QUEUE_TABLE} WHERE order_number = %s",
                    (test_order,),
                )

                cursor.execute(
                    """
                    SELECT run_date, completed_count, no_execution_count, processed
                    FROM assemblers_schedule_apply_daily_cutoff(
                        %s::date,
                        ((%s::date)::timestamp + TIME '18:05') AT TIME ZONE 'Europe/Kyiv'
                    )
                    """,
                    (test_day, test_day),
                )
                cutoff_result = cursor.fetchone()

                cursor.execute(
                    f"""
                    SELECT status, auto_closed_at, auto_close_note
                    FROM {SCHEDULE_TASKS_TABLE}
                    WHERE id = %s
                    """,
                    (task_id,),
                )
                after_task = cursor.fetchone()

                cursor.execute(
                    f"""
                    SELECT assembly_status, assembly_completed_at, install_status, install_completed_at
                    FROM {DETAILS_TABLE_NAME}
                    WHERE id = %s
                    """,
                    (detail_id,),
                )
                after_detail = cursor.fetchone()

                cursor.execute(
                    f"SELECT COUNT(*) FROM {DETAIL_RECALC_QUEUE_TABLE} WHERE order_number = %s",
                    (test_order,),
                )
                queue_count = int(cursor.fetchone()[0])

            _assert(cutoff_result is not None, "Cutoff function did not return a row")
            _assert(after_task is not None, "Schedule task was not found after cutoff")
            _assert(after_task[0] == "Завершено", f"Expected task status 'Завершено', got: {after_task[0]!r}")
            _assert(after_task[1] is not None, "Expected auto_closed_at to be set")
            _assert(
                str(after_task[2] or "").strip() in {
                    "Автоматично завершено після 18:00",
                    "Пауза - завершено автоматично о 18:00",
                },
                f"Unexpected auto_close_note: {after_task[2]!r}",
            )

            _assert(before_detail == after_detail, "Details row changed after auto-cutoff")
            _assert(queue_count == 0, f"Expected no recalc queue row for auto-cutoff, got count={queue_count}")

            print("PASS: auto-cutoff closes only schedule task and does not touch details.")
            print(f"Task id: {task_id}, detail id: {detail_id}")
            print(f"Cutoff result: run_date={cutoff_result[0]}, completed={cutoff_result[1]}, no_exec={cutoff_result[2]}, processed={cutoff_result[3]}")
            print(f"Task after cutoff: status={after_task[0]}, auto_closed_at={after_task[1]}, note={after_task[2]}")
            print(f"Details before: {before_detail}")
            print(f"Details after:  {after_detail}")
            print(f"Recalc queue rows for test order: {queue_count}")
        finally:
            conn.rollback()


def _status_counts(cursor, target_day: date) -> dict[str, int]:
    cursor.execute(
        f"""
        SELECT status, COUNT(*)
        FROM {SCHEDULE_TASKS_TABLE}
        WHERE scheduled_for = %s
        GROUP BY status
        """,
        (target_day,),
    )
    return {str(row[0] or ""): int(row[1] or 0) for row in cursor.fetchall()}


def run_live(*, target_day: date, reset_run_record: bool = False) -> None:
    """Run real daily cutoff logic for a chosen day with forced time > 18:00 Kyiv."""
    ensure_schedule_schema()

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            before_counts = _status_counts(cursor, target_day)

            if reset_run_record:
                cursor.execute(
                    f"DELETE FROM {AUTO_CLOSE_RUNS_TABLE} WHERE run_date = %s",
                    (target_day,),
                )

            cursor.execute(
                """
                SELECT run_date, completed_count, no_execution_count, processed
                FROM assemblers_schedule_apply_daily_cutoff(
                    %s::date,
                    ((%s::date)::timestamp + TIME '18:05') AT TIME ZONE 'Europe/Kyiv'
                )
                """,
                (target_day, target_day),
            )
            cutoff_result = cursor.fetchone()

            after_counts = _status_counts(cursor, target_day)

            cursor.execute(
                f"""
                SELECT COUNT(*)
                FROM {SCHEDULE_TASKS_TABLE}
                WHERE scheduled_for = %s
                  AND auto_closed_at IS NOT NULL
                """,
                (target_day,),
            )
            auto_closed_rows = int(cursor.fetchone()[0])

        conn.commit()

    print("LIVE CUTOFF RUN COMPLETE")
    print(f"Day: {target_day.isoformat()}")
    print(
        "Function result: "
        f"run_date={cutoff_result[0]}, completed_count={cutoff_result[1]}, "
        f"no_execution_count={cutoff_result[2]}, processed={cutoff_result[3]}"
    )
    print(f"Status counts before: {before_counts}")
    print(f"Status counts after:  {after_counts}")
    print(f"Rows with auto_closed_at for day: {auto_closed_rows}")

    if cutoff_result and not cutoff_result[3]:
        print(
            "NOTE: processed=False. This usually means the day is already processed or time check failed. "
            "Use --reset-run-record to re-test the same day."
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run schedule daily cutoff in two modes: "
            "live (real changes, forced after 18:00) or guard (rollback self-test)."
        )
    )
    parser.add_argument(
        "--mode",
        choices=["live", "guard"],
        default="live",
        help="live: apply real cutoff for selected day; guard: rollback-based safety self-test",
    )
    parser.add_argument(
        "--day",
        default=date.today().isoformat(),
        help="Target day in YYYY-MM-DD format (used in live mode). Default: today",
    )
    parser.add_argument(
        "--reset-run-record",
        action="store_true",
        help="Delete record from assemblers_schedule_auto_close_runs for target day before running",
    )
    return parser.parse_args()


if __name__ == "__main__":
    try:
        args = _parse_args()
        if args.mode == "guard":
            run_test()
        else:
            target_day = date.fromisoformat(str(args.day).strip())
            run_live(target_day=target_day, reset_run_record=bool(args.reset_run_record))
    except Exception as exc:
        print(f"FAIL: {exc}")
        raise
