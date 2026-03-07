import json
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, Text
)
from sqlalchemy.orm import relationship

from database import Base


class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    users = relationship("User", back_populates="department")
    items = relationship("KnowledgeItem", back_populates="department")


class DocumentType(Base):
    __tablename__ = "document_types"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    items = relationship("KnowledgeItem", back_populates="document_type")


class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    items = relationship("KnowledgeItem", back_populates="source")


class Status(Base):
    __tablename__ = "statuses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    sort_order = Column(Integer, default=0)
    admin_only = Column(Boolean, default=False)
    color_class = Column(String, default="status-default")
    is_active = Column(Boolean, default=True)

    items = relationship("KnowledgeItem", back_populates="status")
    history_from = relationship(
        "StatusHistory", foreign_keys="StatusHistory.from_status_id", back_populates="from_status"
    )
    history_to = relationship(
        "StatusHistory", foreign_keys="StatusHistory.to_status_id", back_populates="to_status"
    )


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)

    department = relationship("Department", back_populates="users")
    items = relationship("KnowledgeItem", back_populates="owner")
    status_changes = relationship("StatusHistory", back_populates="changed_by")
    audit_logs = relationship("AuditLog", back_populates="actor")


class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    summary = Column(Text, nullable=True)
    text_content = Column(Text, nullable=True)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    document_type_id = Column(Integer, ForeignKey("document_types.id"), nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status_id = Column(Integer, ForeignKey("statuses.id"), nullable=True)
    is_locked = Column(Boolean, default=False)
    review_due_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    source = relationship("Source", back_populates="items")
    department = relationship("Department", back_populates="items")
    document_type = relationship("DocumentType", back_populates="items")
    owner = relationship("User", back_populates="items")
    status = relationship("Status", back_populates="items")
    files = relationship("ItemFile", back_populates="item", cascade="all, delete-orphan")
    status_history = relationship("StatusHistory", back_populates="item", order_by="StatusHistory.created_at")


class ItemFile(Base):
    __tablename__ = "item_files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    item_id = Column(Integer, ForeignKey("knowledge_items.id", ondelete="CASCADE"), nullable=False)
    original_filename = Column(String)
    r2_key = Column(String)
    mime_type = Column(String)
    file_size = Column(Integer)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    item = relationship("KnowledgeItem", back_populates="files")


class StatusHistory(Base):
    __tablename__ = "status_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    item_id = Column(Integer, ForeignKey("knowledge_items.id"), nullable=False)
    from_status_id = Column(Integer, ForeignKey("statuses.id"), nullable=True)
    to_status_id = Column(Integer, ForeignKey("statuses.id"), nullable=False)
    changed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    item = relationship("KnowledgeItem", back_populates="status_history")
    from_status = relationship("Status", foreign_keys=[from_status_id], back_populates="history_from")
    to_status = relationship("Status", foreign_keys=[to_status_id], back_populates="history_to")
    changed_by = relationship("User", back_populates="status_changes")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String)
    target_type = Column(String)
    target_id = Column(String)
    detail = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    actor = relationship("User", back_populates="audit_logs")

    @staticmethod
    def log(db, actor_id, action, target_type="", target_id="", **detail):
        entry = AuditLog(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id),
            detail=json.dumps(detail),
        )
        db.add(entry)
