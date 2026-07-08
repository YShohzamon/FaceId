"""
Page routes — renders Jinja2 HTML templates.
"""

import logging
from datetime import date
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database.connection import get_db
from app.models.student import Student
from app.models.attendance_log import AttendanceLog
from app.core.config import settings
from app.core.network import get_wifi_ipv4_addresses

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)


@router.get("/", response_class=HTMLResponse, name="home")
async def home(request: Request, db: AsyncSession = Depends(get_db)):
    """Dashboard home page."""
    try:
        total_students = await db.scalar(select(func.count(Student.id)))
        today_attendance = await db.scalar(
            select(func.count(AttendanceLog.id))
            .where(AttendanceLog.attendance_date == date.today())
        )
        total_records = await db.scalar(select(func.count(AttendanceLog.id)))

        result = await db.execute(
            select(AttendanceLog)
            .order_by(AttendanceLog.recorded_at.desc())
            .limit(10)
        )
        recent_logs = result.scalars().all()

        for log in recent_logs:
            await db.refresh(log, ["student"])

    except Exception as e:
        logger.error(f"Home page DB error: {e}")
        total_students = 0
        today_attendance = 0
        total_records = 0
        recent_logs = []

    stats = {
        "total_students": total_students or 0,
        "today_attendance": today_attendance or 0,
        "total_records": total_records or 0,
    }

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "stats": stats,
            "recent_logs": recent_logs,
            "active_page": "home",
        },
    )


@router.get("/recognition", response_class=HTMLResponse, name="recognition_page")
async def recognition_page(request: Request):
    """Live recognition page."""
    return templates.TemplateResponse(
        "recognition.html",
        {"request": request, "active_page": "recognition", "gpu_enabled": settings.use_gpu},
    )


@router.get("/add-student", response_class=HTMLResponse, name="add_student_page")
async def add_student_page(request: Request):
    """Add student / enrollment page."""
    return templates.TemplateResponse(
        "add_student.html",
        {"request": request, "active_page": "add_student"},
    )


@router.get("/students", response_class=HTMLResponse, name="student_list_page")
async def student_list_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Student list page."""
    try:
        result = await db.execute(select(Student).order_by(Student.created_at.desc()))
        students = result.scalars().all()

        for student in students:
            await db.refresh(student, ["face_embeddings"])

    except Exception as e:
        logger.error(f"Student list DB error: {e}")
        students = []

    return templates.TemplateResponse(
        "student_list.html",
        {"request": request, "students": students, "active_page": "students"},
    )


@router.get("/attendance", response_class=HTMLResponse, name="attendance_page")
async def attendance_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Today's attendance page."""
    today = date.today()
    try:
        result = await db.execute(
            select(AttendanceLog, Student.name, Student.student_code)
            .join(Student, AttendanceLog.student_id == Student.id)
            .where(AttendanceLog.attendance_date == today)
            .order_by(AttendanceLog.recorded_at.desc())
        )
        rows = result.all()

        logs = [
            {
                "student_name": name,
                "student_code": code,
                "attendance_time": log.attendance_time.strftime("%H:%M:%S"),
                "confidence": log.confidence,
            }
            for log, name, code in rows
        ]

    except Exception as e:
        logger.error(f"Attendance page DB error: {e}")
        logs = []

    return templates.TemplateResponse(
        "attendance.html",
        {
            "request": request,
            "active_page": "attendance",
            "today": str(today),
            "logs": logs,
        },
    )


@router.get("/settings", response_class=HTMLResponse, name="settings_page")
async def settings_page(request: Request):
    """Settings page (placeholder)."""
    lan_ips = get_wifi_ipv4_addresses()
    phone_urls = [f"http://{ip}:8000" for ip in lan_ips]
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "active_page": "settings",
            "config": settings,
            "lan_ips": lan_ips,
            "phone_urls": phone_urls,
        },
    )
