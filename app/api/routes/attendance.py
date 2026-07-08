"""
Attendance API routes.
"""

import logging
from datetime import date, datetime
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel

from app.database.connection import get_db
from app.models.attendance_log import AttendanceLog
from app.models.student import Student

router = APIRouter(prefix="/api/attendance", tags=["attendance"])
logger = logging.getLogger(__name__)


class AttendanceResponse(BaseModel):
    id: int
    student_id: int
    student_name: str
    student_code: str | None = None
    attendance_date: date
    attendance_time: str
    confidence: float
    recorded_at: datetime

    model_config = {"from_attributes": True}


@router.get("/today", response_model=list[AttendanceResponse])
async def get_today_attendance(db: AsyncSession = Depends(get_db)):
    """Return all attendance records for today."""
    result = await db.execute(
        select(AttendanceLog, Student.name, Student.student_code)
        .join(Student, AttendanceLog.student_id == Student.id)
        .where(AttendanceLog.attendance_date == date.today())
        .order_by(AttendanceLog.recorded_at.desc())
    )
    rows = result.all()

    return [
        AttendanceResponse(
            id=log.id,
            student_id=log.student_id,
            student_name=name,
            student_code=code,
            attendance_date=log.attendance_date,
            attendance_time=log.attendance_time.strftime("%H:%M:%S"),
            confidence=log.confidence,
            recorded_at=log.recorded_at,
        )
        for log, name, code in rows
    ]


@router.get("/last")
async def get_last_attendance(db: AsyncSession = Depends(get_db)):
    """Return the most recent attendance record (any day)."""
    result = await db.execute(
        select(AttendanceLog, Student.name)
        .join(Student, AttendanceLog.student_id == Student.id)
        .order_by(AttendanceLog.recorded_at.desc())
        .limit(1)
    )
    row = result.first()

    if not row:
        return {"found": False}

    log, name = row
    return {
        "found": True,
        "student_name": name,
        "attendance_date": str(log.attendance_date),
        "attendance_time": log.attendance_time.strftime("%H:%M:%S"),
        "confidence": round(log.confidence, 3),
        "recorded_at": log.recorded_at.isoformat(),
    }


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Quick stats for the dashboard auto-refresh."""
    total_students = await db.scalar(select(func.count(Student.id))) or 0
    today_attendance = await db.scalar(
        select(func.count(AttendanceLog.id))
        .where(AttendanceLog.attendance_date == date.today())
    ) or 0
    total_records = await db.scalar(select(func.count(AttendanceLog.id))) or 0
    return {
        "total_students": total_students,
        "today_attendance": today_attendance,
        "total_records": total_records,
    }


@router.get("/history")
async def get_attendance_history(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """Return the last N attendance records across all days."""
    result = await db.execute(
        select(AttendanceLog, Student.name)
        .join(Student, AttendanceLog.student_id == Student.id)
        .order_by(AttendanceLog.recorded_at.desc())
        .limit(limit)
    )
    rows = result.all()

    return [
        {
            "id": log.id,
            "student_name": name,
            "date": str(log.attendance_date),
            "time": log.attendance_time.strftime("%H:%M:%S"),
            "confidence": round(log.confidence, 3),
        }
        for log, name in rows
    ]
