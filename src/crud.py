from sqlalchemy.orm import Session

from . import models, schemas


def get_user(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()


def get_user_by_email(db: Session, user_email: str):
    return db.query(models.User).filter(models.User.user_email == user_email).first()


def convert_user_id_to_user_email(db: Session, user_id: int):
    return db.query(models.User.user_email).filter(models.User.id == user_id).scalar()


def convert_user_email_to_user_id(db: Session, user_email: str):
    return (
        db.query(models.User.id).filter(models.User.user_email == user_email).scalar()
    )


def get_user_count(db: Session):
    return db.query(models.User).count()


def get_many_users(db: Session, how_many: int):
    return db.query(models.User).limit(how_many).all()


def get_user_received_messages(db: Session, user_id: int):
    return db.query(models.Message).filter(models.Message.receiver_id == user_id).all()


def get_user_sent_messages(db: Session, user_id: int):
    return db.query(models.Message).filter(models.Message.sender_id == user_id).all()


def create_registered_user(db: Session, email: str, username: str):
    db_user = models.User(user_email=email, user_name=username)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


# def create_user(db: Session, user: schemas.UserCreate):
#     hashed_password = hash_password(user.password)
#     db_user = models.User(user_name=user.user_email, hashed_password=hashed_password)
#     db.add(db_user)
#     db.commit()
#     db.refresh(db_user)
#     return db_user


def create_message(
    db: Session, message: schemas.MessageCreate, sender_id: int, receiver_id: int
):
    db_message = models.Message(
        content=message.content, sender_id=sender_id, receiver_id=receiver_id
    )
    db.add(db_message)
    db.commit()
    db.refresh(db_message)
    return db_message
