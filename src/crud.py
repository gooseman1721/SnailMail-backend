from sqlalchemy.orm import Session

from . import models, schemas

def get_user(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()

def get_user_by_username(db: Session, username: str):
    return db.query(models.User).filter(models.User.user_name == username).first()

def get_user_count(db: Session):
    return db.query(models.User).count()

def get_many_users(db: Session, how_many: int):
    return db.query(models.User).limit(how_many).all()

def get_user_received_messages(db: Session, user_id: int):
    return db.query(models.Message).filter(
        models.Message.receiver_id == user_id).all()

def create_user(db: Session, user: schemas.UserCreate):
    not_hashed_password = user.password + "hashash"
    db_user = models.User(user_name=user.user_name, hashed_password=not_hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def create_message(db: Session, message: schemas.MessageCreate, sender_id: int, receiver_id: int):
    db_message = models.Message(content=message.content, sender_id=sender_id, receiver_id=receiver_id)
    db.add(db_message)
    db.commit()
    db.refresh(db_message)
    return(db_message)