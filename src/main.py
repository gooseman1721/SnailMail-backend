from datetime import datetime
from pydantic import BaseModel

from fastapi import Depends, FastAPI, HTTPException, status, Request
from fastapi.security import (
    OAuth2AuthorizationCodeBearer,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from starlette.middleware.cors import CORSMiddleware

from fief_client import FiefAccessTokenInfo, FiefAsync
from fief_client.integrations.fastapi import FiefAuth

from sqlalchemy.orm import Session
import uvicorn

from . import crud, models, schemas
from .database import SessionLocal, engine
from .constants import FIEF_BASE_URL, CLIENT_ID, CLIENT_SECRET, ALLOWED_ORIGINS

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


class BasicResponse(BaseModel):
    response_text: str


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/ping/", response_model=BasicResponse)
def ping():
    time = datetime.utcnow()
    return {"response_text": str(time)}


@app.post("/user_login_and_get_data/", response_model=schemas.User)
async def user_login_and_get_data(
    access_token_info: FiefAccessTokenInfo = Depends(auth.authenticated()),
    db: Session = Depends(get_db),
):
    email = fief.userinfo(access_token_info.access_token).email
    db_user_in_db = crud.get_user_by_username(db=db, user_name=email)
    if not db_user_in_db:
        return crud.create_registered_user(db=db, email=email)
    return db_user_in_db


@app.post("/users/", response_model=schemas.User)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_username(db=db, user_name=user.user_name)
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


@app.get("/users/all/", response_model=list[schemas.User])
def get_all_users(db: Session = Depends(get_db)):
    user_count = crud.get_user_count(db=db)
    users = crud.get_many_users(db=db, how_many=user_count)

    return users


@app.post("/messages/")
def create_message(
    message: schemas.MessageCreate,
    sender_name: str,
    receiver_name: str,
    db: Session = Depends(get_db),
    access_token_info: FiefAccessTokenInfo = Depends(auth.authenticated()),
):

    token_data = fief.userinfo(access_token_info.access_token)
    user_id = crud.convert_user_name_to_user_id(db=db, user_name=token_data.email)

    try:
        sender_id = crud.convert_user_name_to_user_id(db=db, user_name=sender_name)
    except:
        raise HTTPException(status_code=404, detail="Sender username not found")

    try:
        receiver_id = crud.convert_user_name_to_user_id(db=db, user_name=receiver_name)
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
    user = crud.get_user_by_username(db=db, user_name=token_data.email)
    return user


@app.get("/users/me/my_messages/received", response_model=list[schemas.Message])
def read_users_me_messages_received(
    access_token_info: FiefAccessTokenInfo = Depends(auth.authenticated()),
    db: Session = Depends(get_db),
):
    token_data = fief.userinfo(access_token_info.access_token)
    received_messages = crud.get_user_received_messages(
        db=db,
        user_id=crud.convert_user_name_to_user_id(db=db, user_name=token_data.email),
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
        user_id=crud.convert_user_name_to_user_id(db=db, user_name=token_data.email),
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


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
