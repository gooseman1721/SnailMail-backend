from datetime import datetime
from pydantic import BaseModel

# Messages


class MessageBase(BaseModel):
    content: str


class MessageCreate(MessageBase):
    pass


class Message(MessageBase):
    id: int
    sender_id: int
    receiver_id: int
    created_datetime: datetime

    class Config:
        orm_mode = True


# Users


class UserBase(BaseModel):
    user_email: str


class UserCreate(UserBase):
    pass


class User(UserBase):
    id: int
    is_online: bool
    user_name: str
    sent_messages: list[Message] = []
    received_messages: list[Message] = []

    class Config:
        orm_mode = True


class UserDisplay(BaseModel):
    id: int
    is_online: bool
    user_name: str

    class Config:
        orm_mode = True


class UserId(BaseModel):
    id: int

class SendMessageSchema(BaseModel):
    content: str


# Tokens


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str | None = None
