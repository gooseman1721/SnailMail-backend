from datetime import datetime
from pydantic import BaseModel
import re

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    status,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.security import (
    OAuth2AuthorizationCodeBearer,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from starlette.middleware.cors import CORSMiddleware

from fief_client import (
    FiefAccessTokenInfo,
    FiefAsync,
    FiefUserInfo,
    FiefAccessTokenInvalid,
    FiefAccessTokenExpired,
)
from fief_client.integrations.fastapi import FiefAuth

from sqlalchemy.orm import Session
import uvicorn

from . import crud, models, schemas
from .database import SessionLocal, engine
from .constants import (
    FIEF_BASE_URL,
    CLIENT_ID,
    CLIENT_SECRET,
    ALLOWED_ORIGINS,
    EMAIL_REGEX,
)

models.Base.metadata.create_all(bind=engine)


fief = FiefAsync(
    FIEF_BASE_URL,
    CLIENT_ID,
    CLIENT_SECRET,
)

scheme = OAuth2AuthorizationCodeBearer(
    str(FIEF_BASE_URL + "/authorize"),
    str(FIEF_BASE_URL + "/token"),
    scopes={"openid": "openid", "offline_access": "offline_access"},
)

auth = FiefAuth(fief, scheme)

app = FastAPI()

origins = ALLOWED_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

email_regex = re.compile(EMAIL_REGEX)


class BasicResponse(BaseModel):
    response_text: str


class UserChatMessages(BaseModel):
    from_user_id: int
    all_messages: list[schemas.Message] = []


class SingleConnection(BaseModel):
    user_id: int
    websocket: WebSocket

    class Config:
        arbitrary_types_allowed = True


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[SingleConnection] = []

    def append_connection(self, user_id: int, websocket: WebSocket):
        self.active_connections.append(
            SingleConnection(user_id=user_id, websocket=websocket)
        )

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(
            SingleConnection(user_id=user_id, websocket=websocket)
        )

    def disconnect(self, websocket: WebSocket):
        self.active_connections = [
            connection
            for connection in self.active_connections
            if connection.websocket != websocket
        ]

    async def notify_user_of_message(self, recipient_id: str):
        for connection in self.active_connections:
            if connection.user_id == recipient_id:
                await connection.websocket.send_text("new message")


connections = ConnectionManager()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Endpoints ------------------------------------------------------------------


@app.get("/ping/", response_model=BasicResponse)
def ping():
    time = datetime.utcnow()
    return {"response_text": str(time)}


@app.get("/user_login_and_get_data/", response_model=schemas.User)
async def user_login_and_get_data(
    access_token_info: FiefAccessTokenInfo = Depends(auth.authenticated()),
    db: Session = Depends(get_db),
):

    userinfo = await fief.userinfo(access_token_info["access_token"])
    email = userinfo["email"]
    db_user_in_db = crud.get_user_by_email(db=db, user_email=email)
    if not db_user_in_db:
        username = userinfo["fields"]["username"]
        return crud.create_registered_user(db=db, email=email, username=username)
    return db_user_in_db


@app.post("/users/", response_model=schemas.User)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_email(db=db, user_email=user.user_email)
    if db_user:
        raise HTTPException(status_code=400, detail="Username already exists")

    return crud.create_user(db=db, user=user)


@app.get("/users/", response_model=list[schemas.User])
def get_many_users(user_count_to_return: int = 1, db: Session = Depends(get_db)):
    user_count = crud.get_user_count(db=db)
    if user_count_to_return > user_count:
        user_count_to_return = user_count

    users = crud.get_many_users(db=db, how_many=user_count_to_return)

    return users


@app.get("/users/{user_id}", response_model=schemas.User)
def get_user(user_id: int, db: Session = Depends(get_db)):
    db_user = crud.get_user(db=db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")

    return db_user


@app.get("/users/{user_id}/messages/", response_model=list[schemas.Message])
def get_user_received_messages(user_id: int, db: Session = Depends(get_db)):
    db_user = crud.get_user(db=db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return crud.get_user_received_messages(db=db, user_id=user_id)


@app.get("/users/all/", response_model=list[schemas.UserDisplay])
def get_all_users(db: Session = Depends(get_db)):
    user_count = crud.get_user_count(db=db)
    users = crud.get_many_users(db=db, how_many=user_count)

    return users


@app.post("/send_message/")
async def send_message(
    message: schemas.MessageCreate,
    sender_id: int,
    receiver_id: int,
    db: Session = Depends(get_db),
    access_token_info: FiefAccessTokenInfo = Depends(auth.authenticated()),
):

    userinfo = await fief.userinfo(access_token_info["access_token"])
    user_id = crud.convert_user_email_to_user_id(db=db, user_email=userinfo["email"])

    try:
        sender = crud.get_user(db=db, user_id=sender_id)
    except:
        raise HTTPException(status_code=404, detail="Invalid sender")

    try:
        receiver = crud.get_user(db=db, user_id=receiver_id)
    except:
        raise HTTPException(status_code=404, detail="Invalid receiver")
    # some func that checks if user can send the message (permissions, blocks, bans)...

    if user_id != sender_id:
        raise HTTPException(status_code=401, detail="Token and user id mismatch")

    return crud.create_message(
        db=db, message=message, sender_id=sender_id, receiver_id=receiver_id
    )


@app.post("/messages/")
async def create_message(
    message: schemas.MessageCreate,
    sender_name: str,
    receiver_name: str,
    db: Session = Depends(get_db),
    access_token_info: FiefAccessTokenInfo = Depends(auth.authenticated()),
):

    userinfo = await fief.userinfo(access_token_info["access_token"])
    user_id = crud.convert_user_email_to_user_id(db=db, user_email=userinfo["email"])

    try:
        sender_id = crud.convert_user_email_to_user_id(db=db, user_email=sender_name)
    except:
        raise HTTPException(status_code=404, detail="Sender username not found")

    try:
        receiver_id = crud.convert_user_email_to_user_id(
            db=db, user_email=receiver_name
        )
    except:
        raise HTTPException(status_code=404, detail="Receiver username not found")

    if user_id != sender_id:
        raise HTTPException(status_code=401, detail="Token and user id mismatch")

    db_receiver = crud.get_user(db=db, user_id=receiver_id)

    if db_receiver is None:
        raise HTTPException(status_code=404, detail="Receiver not found")

    return crud.create_message(
        db=db, message=message, sender_id=sender_id, receiver_id=receiver_id
    )


@app.get("/users/me/", response_model=schemas.User)
def read_users_me(
    access_token_info: FiefAccessTokenInfo = Depends(auth.authenticated()),
    db: Session = Depends(get_db),
):
    token_data = fief.userinfo(access_token_info.access_token)
    user = crud.get_user_by_email(db=db, user_email=token_data.email)
    return user


@app.get("/users/me/my_messages/received", response_model=list[schemas.Message])
def read_users_me_messages_received(
    access_token_info: FiefAccessTokenInfo = Depends(auth.authenticated()),
    db: Session = Depends(get_db),
):
    token_data = fief.userinfo(access_token_info.access_token)
    received_messages = crud.get_user_received_messages(
        db=db,
        user_id=crud.convert_user_email_to_user_id(db=db, user_email=token_data.email),
    )
    return received_messages


@app.get("/users/me/my_messages/sent", response_model=list[schemas.Message])
def read_users_me_messages_sent(
    access_token_info: FiefAccessTokenInfo = Depends(auth.authenticated()),
    db: Session = Depends(get_db),
):
    token_data = fief.userinfo(access_token_info.access_token)
    sent_messages = crud.get_user_sent_messages(
        db=db,
        user_id=crud.convert_user_email_to_user_id(db=db, user_email=token_data.email),
    )
    return sent_messages


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=jsonable_encoder({"detail": exc.errors(), "body": exc.body}),
    )


@app.get("/fief_user/")
async def get_fief_user(
    access_token_info: FiefAccessTokenInfo = Depends(auth.authenticated()),
):
    return access_token_info


@app.post("/user/friends/requests/send")
async def send_friendship_request(
    adressee_id: schemas.UserId,
    db: Session = Depends(get_db),
    access_token_info: FiefAccessTokenInfo = Depends(auth.authenticated()),
):
    requester_id = await get_auth_user_id(db=db, access_token_info=access_token_info)
    db_adressee = crud.get_user(db=db, user_id=adressee_id.id)

    if requester_id == adressee_id.id:
        raise HTTPException(status_code=400, detail="Bad request")
    if db_adressee is None:
        raise HTTPException(status_code=400, detail="Bad request")

    friendship = crud.get_friendship(
        db=db, first_user=requester_id, second_user=adressee_id.id
    )
    if friendship:
        friendship_status = crud.get_most_recent_friendship_status(
            db=db, friendship=friendship
        )
        match friendship_status.status_code:
            case "R":
                raise HTTPException(
                    status_code=400, detail="Friend request already sent"
                )
            case "A":
                raise HTTPException(
                    status_code=400, detail="Friend request already accepted"
                )
            case "D":
                raise HTTPException(status_code=403, detail="Friend request denied")
            case "B":
                raise HTTPException(status_code=403, detail="Blocked by user")

    return crud.create_friendship_request(
        db=db, requester_id=requester_id, adressee_id=adressee_id.id
    )


# @app.get("/user/friends/requests/")
# async def get_friendship_requests(
#     db: Session = Depends(get_db),
#     access_token_info: FiefAccessTokenInfo = Depends(auth.authenticated()),
# ):
#     this_user_id = await get_auth_user_id(db=db, access_token_info=access_token_info)
#     return crud.get_friendship_requests_to_this_user(db=db, this_user=this_user_id)


@app.post("/user/friends/requests/accept/")
async def accept_friendship_request(
    requester_id: schemas.UserId,
    db: Session = Depends(get_db),
    access_token_info: FiefAccessTokenInfo = Depends(auth.authenticated()),
):
    this_user_id = await get_auth_user_id(db=db, access_token_info=access_token_info)
    friendship_requests = crud.get_friendship_requests_to_this_user(
        db=db, this_user=this_user_id
    )
    for request in friendship_requests:
        if request.requester_id == requester_id.id:
            return crud.accept_friendship_request(
                db=db, this_user=this_user_id, other_user=requester_id.id
            )
    raise HTTPException(status_code=404, detail="Friendship requester not found")


@app.get("/user/friends/", response_model=list[schemas.UserDisplay])
async def get_user_friends(
    db: Session = Depends(get_db),
    access_token_info: FiefAccessTokenInfo = Depends(auth.authenticated()),
):
    this_user_id = await get_auth_user_id(db=db, access_token_info=access_token_info)

    return crud.get_user_friends(db=db, this_user=this_user_id)


@app.get("/user/friends/requests/", response_model=list[schemas.UserDisplay])
async def get_users_that_requested_friends_to_user(
    db: Session = Depends(get_db),
    access_token_info: FiefAccessTokenInfo = Depends(auth.authenticated()),
):
    this_user_id = await get_auth_user_id(db=db, access_token_info=access_token_info)

    return crud.get_users_who_requested_friends_to_this_user(
        db=db, this_user=this_user_id
    )


@app.get("/user/friends/{friend_id}/messages/", response_model=UserChatMessages)
async def get_friend_messages(
    friend_id: int,
    db: Session = Depends(get_db),
    access_token_info: FiefAccessTokenInfo = Depends(auth.authenticated()),
):
    this_user_id = await get_auth_user_id(db=db, access_token_info=access_token_info)

    user_friends = crud.get_user_friends(db=db, this_user=this_user_id)
    friend = crud.get_user(db=db, user_id=friend_id)

    if friend not in user_friends:
        raise HTTPException(status_code=403, detail="Forbidden")

    all_messages = crud.get_friend_messages_sorted(
        db=db, user_id=this_user_id, friend_id=friend_id
    )
    return {
        "from_user_id": friend_id,
        "all_messages": all_messages,
    }


@app.post("/user/friends/{friend_id}/messages/", response_model=schemas.Message)
async def send_message(
    message_text: schemas.SendMessageSchema,
    friend_id: int,
    db: Session = Depends(get_db),
    access_token_info: FiefAccessTokenInfo = Depends(auth.authenticated()),
):

    this_user_id = await get_auth_user_id(db=db, access_token_info=access_token_info)

    user_friends = crud.get_user_friends(db=db, this_user=this_user_id)
    friend = crud.get_user(db=db, user_id=friend_id)

    if friend not in user_friends:
        raise HTTPException(status_code=403, detail="Forbidden")

    message = crud.create_message(
        db=db, message=message_text, sender_id=this_user_id, receiver_id=friend_id
    )

    await connections.notify_user_of_message(friend_id)

    return message


@app.websocket("/ws_new_chat_message/{socket_id}/")
async def ws_new_chat_messages(
    websocket: WebSocket,
    socket_id: int,
    db: Session = Depends(get_db),
):
    await websocket.accept()
    websocket_auth = await websocket.receive_json()
    email = websocket_auth["email"]
    access_token = websocket_auth["access_token"]

    if re.fullmatch(email_regex, email) is False:
        print("WebSocket message is not a valid email")
        websocket.close(reason="Invalid email")
        raise ValueError("Invalid email error")

    try:
        fief.validate_access_token(access_token)
    except FiefAccessTokenInvalid:
        websocket.close(reason="Failed to authorize")
    except FiefAccessTokenExpired:
        websocket.close(reason="Access token expired")

    this_user_id = crud.convert_user_email_to_user_id(db, email)
    if this_user_id is None:
        websocket.close(reason="Invalid email")
        raise ValueError("DB error")

    connections.append_connection(this_user_id, websocket)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connections.disconnect(websocket)


# DEV ONLY!!!
@app.delete("/user/friends/requests/")
async def delete_friendships(db: Session = Depends(get_db)):
    return crud.delete_friendships(db=db)


@app.post("/send_message_DEV/")
async def send_message(
    message: schemas.MessageCreate,
    sender_id: int,
    receiver_id: int,
    db: Session = Depends(get_db),
):

    return crud.create_message(
        db=db, message=message, sender_id=sender_id, receiver_id=receiver_id
    )


# Helper functions ------------------------------------------------------------------

# returns user_id of current user
async def get_auth_user_id(db: Session, access_token_info: FiefAccessTokenInfo):
    userinfo = await fief.userinfo(access_token_info["access_token"])
    return crud.convert_user_email_to_user_id(db=db, user_email=userinfo["email"])


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7000)
