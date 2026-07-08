"""
Student service — database operations for creating and managing students.
"""

import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.student import Student
from app.models.face_embedding import FaceEmbedding

logger = logging.getLogger(__name__)


async def create_student(
    db: AsyncSession,
    name: str,
    student_code: str | None = None,
) -> Student:
    """Insert a new student and return the created record."""
    student = Student(name=name.strip(), student_code=student_code)
    db.add(student)
    await db.commit()
    await db.refresh(student)
    logger.info(f"Student created: {student.name} (id={student.id})")
    return student


async def save_face_image_record(
    db: AsyncSession,
    student_id: int,
    image_path: str,
    angle_label: str,
) -> FaceEmbedding:
    """
    Save a face image record to DB (embedding_path is empty for now —
    it will be filled in Phase 6 when we generate the actual embedding).
    """
    record = FaceEmbedding(
        student_id=student_id,
        image_path=image_path,
        embedding_path="",   # Filled in Phase 6
        angle_label=angle_label,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def get_student_by_id(db: AsyncSession, student_id: int) -> Student | None:
    return await db.get(Student, student_id)


async def get_all_active_students(db: AsyncSession) -> list[Student]:
    result = await db.execute(
        select(Student).where(Student.is_active == True).order_by(Student.name)
    )
    return result.scalars().all()


async def delete_student(db: AsyncSession, student_id: int) -> bool:
    student = await db.get(Student, student_id)
    if not student:
        return False
    await db.delete(student)
    await db.commit()
    logger.info(f"Student deleted: {student.name} (id={student_id})")
    return True
