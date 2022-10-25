from sqlalchemy.orm import Session
from sqlalchemy.sql import or_, and_

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


def get_friend_messages_sorted(
    db: Session,
    user_id: int,
    friend_id: int,
):
    all_messages = (
        db.query(models.Message)
        .filter(
            or_(
                and_(
                    models.Message.sender_id == user_id,
                    models.Message.receiver_id == friend_id,
                ),
                and_(
                    models.Message.sender_id == friend_id,
                    models.Message.receiver_id == user_id,
                ),
            )
        )
        .order_by(models.Message.created_datetime.desc())
        .all()
    )
    return all_messages


# Friendships ------------------------------------------------------------------


def create_friendship_request(db: Session, requester_id: int, adressee_id: int):
    db_new_friendship = models.Friendship(
        requester_id=requester_id, adressee_id=adressee_id
    )

    db.add(db_new_friendship)
    db.commit()
    db.refresh(db_new_friendship)

    db_new_friendship_status = models.FriendshipStatus(
        requester_id=requester_id,
        adressee_id=adressee_id,
        specifier_id=requester_id,
        status_code="R",
    )

    db.add(db_new_friendship_status)
    db.commit()
    db.refresh(db_new_friendship_status)

    return db_new_friendship, db_new_friendship_status


def get_friendship(db: Session, first_user: int, second_user: int):
    friendship = db.query(models.Friendship).get((first_user, second_user))
    if friendship is None:
        friendship = db.query(models.Friendship).get((second_user, first_user))

    return friendship


def get_user_friends(db: Session, this_user: int):
    friendships = (
        db.query(models.Friendship)
        .filter(
            (models.Friendship.adressee_id == this_user)
            | (models.Friendship.requester_id == this_user)
        )
        .all()
    )
    if not friendships:
        return []

    friends = []
    for friendship in friendships:
        most_recent_friendship_status = (
            db.query(models.FriendshipStatus)
            .filter(
                models.FriendshipStatus.adressee_id == friendship.adressee_id,
                models.FriendshipStatus.requester_id == friendship.requester_id,
            )
            .order_by(models.FriendshipStatus.created_datetime.desc())
            .first()
        )
        if (
            most_recent_friendship_status.status_code == "A"
            or most_recent_friendship_status.status_code == "B"
        ):
            # friendships_accepted.append(most_recent_friendship_status)
            friend_id = (
                lambda this_user_id: friendship.requester_id
                if this_user_id == friendship.adressee_id
                else friendship.adressee_id
            )
            friends.append(
                db.query(models.User)
                .filter(models.User.id == friend_id(this_user))
                .first()
            )
    return friends


def get_users_who_requested_friends_to_this_user(db: Session, this_user: int):
    friendships = (
        db.query(models.Friendship)
        .filter(models.Friendship.adressee_id == this_user)
        .all()
    )
    if not friendships:
        return []

    friends = []
    for friendship in friendships:
        most_recent_friendship_status = (
            db.query(models.FriendshipStatus)
            .filter(
                models.FriendshipStatus.adressee_id == friendship.adressee_id,
                models.FriendshipStatus.requester_id == friendship.requester_id,
            )
            .order_by(models.FriendshipStatus.created_datetime.desc())
            .first()
        )
        if most_recent_friendship_status.status_code == "R":
            friend_id = (
                lambda this_user_id: friendship.requester_id
                if this_user_id == friendship.adressee_id
                else friendship.adressee_id
            )
            friends.append(
                db.query(models.User)
                .filter(models.User.id == friend_id(this_user))
                .first()
            )
    return friends


def get_most_recent_friendship_status(db: Session, friendship: models.Friendship):
    friendship_status = (
        db.query(models.FriendshipStatus)
        .filter(
            models.FriendshipStatus.adressee_id == friendship.adressee_id,
            models.FriendshipStatus.requester_id == friendship.requester_id,
        )
        .order_by(models.FriendshipStatus.created_datetime.desc())
        .first()
    )

    return friendship_status


def get_friendship_requests_to_this_user(db: Session, this_user: int):
    friendships = (
        db.query(models.Friendship)
        .filter(models.Friendship.adressee_id == this_user)
        .all()
    )
    if not friendships:
        return []

    friendship_requests = []
    for friendship in friendships:
        most_recent_friendship_status = (
            db.query(models.FriendshipStatus)
            .filter(
                models.FriendshipStatus.adressee_id == friendship.adressee_id,
                models.FriendshipStatus.requester_id == friendship.requester_id,
            )
            .order_by(models.FriendshipStatus.created_datetime.desc())
            .first()
        )
        if most_recent_friendship_status.status_code == "R":
            friendship_requests.append(most_recent_friendship_status)

    return friendship_requests


def accept_friendship_request(db: Session, this_user: int, other_user: int):
    friendship = db.query(models.Friendship).get((other_user, this_user))
    if friendship is None:
        return "DB ERROR: NO FRIENDSHIP FOUND"

    db_new_friendship_status = models.FriendshipStatus(
        requester_id=other_user,
        adressee_id=this_user,
        specifier_id=this_user,
        status_code="A",
    )

    db.add(db_new_friendship_status)
    db.commit()
    db.refresh(db_new_friendship_status)

    return db_new_friendship_status


def deny_friendship_request(db: Session, this_user: int, other_user: int):
    friendship = db.query(models.Friendship).get((other_user, this_user))
    if friendship is None:
        return "DB ERROR: NO FRIENDSHIP FOUND"

    db_new_friendship_status = models.FriendshipStatus(
        requester_id=other_user,
        adressee_id=this_user,
        specifier_id=this_user,
        status_code="D",
    )

    db.add(db_new_friendship_status)
    db.commit()
    db.refresh(db_new_friendship_status)

    return db_new_friendship_status


# Unblock needed as well
def block_friendship(db: Session, this_user: int, other_user: int):
    friendship = db.query(models.Friendship).get((other_user, this_user))
    if friendship is None:
        friendship = db.query(models.Friendship).get((this_user, other_user))
        if friendship is None:
            return "DB ERROR: NO FRIENDSHIP FOUND"

        db_new_friendship_status = models.FriendshipStatus(
            requester_id=this_user,
            adressee_id=other_user,
            specifier_id=this_user,
            status_code="B",
        )
    else:
        db_new_friendship_status = models.FriendshipStatus(
            requester_id=other_user,
            adressee_id=this_user,
            specifier_id=this_user,
            status_code="B",
        )

    db.add(db_new_friendship_status)
    db.commit()
    db.refresh(db_new_friendship_status)

    return db_new_friendship_status


def delete_friendships(db: Session):
    deleted_friendship_status = db.query(models.FriendshipStatus).delete()
    deleted_friendship = db.query(models.Friendship).delete()
    db.commit()

    return deleted_friendship_status, deleted_friendship
