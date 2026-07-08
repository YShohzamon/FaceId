"""
Attendance service.

Handles:
  - Writing attendance records to DB
  - Cooldown: a student cannot be logged twice within COOLDOWN seconds
  - In-memory cooldown tracker to avoid DB hit on every frame

Cooldown design:
  The cooldown dict lives in memory: {student_id: last_logged_datetime}
  On each recognition result we check the in-memory dict first.
  If the cooldown has expired we write to DB and update the dict.
  This means at most one DB write per cooldown period per student.
"""

import logging
from datetime import datetime, date, timezone, timedelta

from app.core.config import settings

logger = logging.getLogger(__name__)

# In-memory cooldown tracker: {student_id: datetime_of_last_log (UTC)}
_cooldown: dict[int, datetime] = {}


def is_on_cooldown(student_id: int) -> bool:
    """Return True if this student was logged within the cooldown window."""
    last = _cooldown.get(student_id)
    if last is None:
        return False
    elapsed = (datetime.now(tz=timezone.utc) - last).total_seconds()
    return elapsed < settings.attendance_cooldown_seconds


def update_cooldown(student_id: int) -> None:
    """Mark the student as just logged."""
    _cooldown[student_id] = datetime.now(tz=timezone.utc)


def reset_cooldown(student_id: int | None = None) -> None:
    """
    Clear cooldown for one student or all students.
    Used in testing or when the camera is stopped.
    """
    if student_id is not None:
        _cooldown.pop(student_id, None)
    else:
        _cooldown.clear()


async def log_attendance(
    db,
    student_id: int,
    student_name: str,
    confidence: float,
) -> bool:
    """
    Write an attendance record if the student is not on cooldown.

    Returns True if a record was written, False if skipped (cooldown).
    """
    if is_on_cooldown(student_id):
        return False

    now_utc = datetime.now(tz=timezone.utc)

    from app.models.attendance_log import AttendanceLog

    record = AttendanceLog(
        student_id=student_id,
        confidence=confidence,
        attendance_date=now_utc.date(),
        attendance_time=now_utc.timetz(),
        recorded_at=now_utc,
    )
    db.add(record)
    await db.commit()

    update_cooldown(student_id)
    logger.info(
        f"Attendance logged: {student_name} (id={student_id}) "
        f"confidence={confidence:.3f}"
    )
    return True
