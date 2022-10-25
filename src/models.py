from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    DateTime,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import expression
from sqlalchemy.ext.compiler import compiles

from .database import Base


class utcnow(expression.FunctionElement):
    type = DateTime()
    inherit_cache = True


@compiles(utcnow, "postgresql")
def pg_utcnow(element, compiler, **kw):
    return "TIMEZONE('utc', CURRENT_TIMESTAMP)"


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    content = Column(String(1000))
    sender_id = Column(Integer, ForeignKey("users.id"))
    receiver_id = Column(Integer, ForeignKey("users.id"))
    created_datetime = Column(DateTime, server_default=utcnow())

    sender = relationship(
        "User", back_populates="sent_messages", foreign_keys=[sender_id]
    )
    receiver = relationship(
        "User", back_populates="received_messages", foreign_keys=[receiver_id]
    )


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    user_email = Column(String(254), unique=True, index=True)
    is_online = Column(Boolean, default=True)
    user_name = Column(String(64))

    sent_messages = relationship(
        "Message", back_populates="sender", foreign_keys=[Message.sender_id]
    )
    received_messages = relationship(
        "Message", back_populates="receiver", foreign_keys=[Message.receiver_id]
    )


class Friendship(Base):
    __tablename__ = "friendships"

    requester_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    adressee_id = Column(Integer, ForeignKey("users.id"), primary_key=True)

    created_datetime = Column(DateTime, server_default=utcnow())


class FriendshipStatus(Base):
    __tablename__ = "friendship_status"

    requester_id = Column(Integer, primary_key=True)
    adressee_id = Column(Integer, primary_key=True)
    __table_args__ = (
        ForeignKeyConstraint(
            [requester_id, adressee_id],
            ["friendships.requester_id", "friendships.adressee_id"],
        ),
        {},
    )

    created_datetime = Column(DateTime, server_default=utcnow(), primary_key=True)

    # Status codes: (R)equested, (A)ccepted, (D)enied, (B)locked
    status_code = Column(String(1), nullable=False)

    # Specifier = who set this status
    specifier_id = Column(Integer, ForeignKey("users.id"), nullable=False)
