"""
Students API routes — CRUD operations.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.database.connection import get_db
from app.models.student import Student

router = APIRouter(prefix="/api/students", tags=["students"])
logger = logging.getLogger(__name__)


class StudentCreate(BaseModel):
    name: str
    student_code: str | None = None


class StudentResponse(BaseModel):
    id: int
    name: str
    student_code: str | None
    is_active: bool

    model_config = {"from_attributes": True}


@router.get("/", response_model=list[StudentResponse])
async def list_students(db: AsyncSession = Depends(get_db)):
    """Return all active students."""
    result = await db.execute(
        select(Student).where(Student.is_active == True).order_by(Student.name)
    )
    return result.scalars().all()


@router.post("/", response_model=StudentResponse, status_code=status.HTTP_201_CREATED)
async def create_student(payload: StudentCreate, db: AsyncSession = Depends(get_db)):
    """Create a new student record."""
    student = Student(name=payload.name.strip(), student_code=payload.student_code)
    db.add(student)
    await db.commit()
    await db.refresh(student)
    logger.info(f"Student created: {student.name} (id={student.id})")
    return student


@router.delete("/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_student(student_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a student and all their face data (cascade)."""
    student = await db.get(Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    await db.delete(student)
    await db.commit()
    logger.info(f"Student deleted: {student.name} (id={student_id})")
