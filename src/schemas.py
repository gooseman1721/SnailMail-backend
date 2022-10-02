from pydantic import BaseModel


class MessageBase(BaseModel):
    content: str


class MessageCreate(MessageBase):
    pass


class Message(MessageBase):
    id: int
    sender_id: int
    receiver_id: int

    class Config:
        orm_mode = True


class UserBase(BaseModel):
    user_name: str


class UserCreate(UserBase):
    password: str


class User(UserBase):
    id: int
    is_online: bool
    sent_messages: list[Message] = []
    received_messages: list[Message] = []

    class Config:
        orm_mode = True


class Token(BaseModel):
    access_token: str
    token_type: str
