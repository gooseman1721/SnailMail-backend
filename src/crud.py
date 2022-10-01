from sqlalchemy.orm import Session
from argon2 import PasswordHasher

from . import models, schemas

ph = PasswordHasher()


def get_user(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()


def get_user_by_username(db: Session, user_name: str):
    return db.query(models.User).filter(models.User.user_name == user_name).first()


def get_user_count(db: Session):
    return db.query(models.User).count()


def get_many_users(db: Session, how_many: int):
    return db.query(models.User).limit(how_many).all()


def get_user_received_messages(db: Session, user_id: int):
    return db.query(models.Message).filter(
        models.Message.receiver_id == user_id).all()


def create_user(db: Session, user: schemas.UserCreate):
    hashed_password = hash_password(user.password)
    db_user = models.User(user_name=user.user_name, hashed_password=hashed_password)
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


def hash_password(cleartext_password):
    return ph.hash(cleartext_password)


def verify_password(password, hashed_password):
    try:
        print(ph.verify(hashed_password, password))
        ph.verify(hashed_password, password)
    except:
        return False
    else:
        if ph.check_needs_rehash(hashed_password):
            new_password = ph.hash(password)
            # put new password into db..
        return True

def get_user_hashed_password(db: Session, user_name: str):
    return db.query(models.User.hashed_password).filter(models.User.user_name == user_name).scalar()
