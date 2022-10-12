from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from .database import Base


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    content = Column(String(1000))
    sender_id = Column(Integer, ForeignKey("users.id"))
    receiver_id = Column(Integer, ForeignKey("users.id"))

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
