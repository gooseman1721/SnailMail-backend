from datetime import datetime, timedelta
from pydantic import BaseModel

from fastapi import Depends, FastAPI, HTTPException, status, Request, Response
from fastapi.security import (
    OAuth2PasswordBearer,
    OAuth2PasswordRequestForm,
    OAuth2AuthorizationCodeBearer,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from starlette.middleware.cors import CORSMiddleware

from fief_client import FiefAccessTokenInfo, FiefAsync
from fief_client.integrations.fastapi import FiefAuth

from sqlalchemy.orm import Session
from jose import JWTError, jwt
import uvicorn

from . import crud, models, schemas
from .database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)

# openssl rand -hex 32
SECRET_KEY = "835bc2696948b6a858506058675922bf67e19d3f49b065bb12c884b2f5a27016"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120


fief = FiefAsync(
    "http://localhost:9000",
    "Ey1OLDHRZlQhCRi9eXFrELu_LQMGaDfqM9JoJ4RJ2C8",
    "FSrK7Sqzd8oGvARjcMkRJfx5iSUfaP4NmABbLP_S4ww",
)

scheme = OAuth2AuthorizationCodeBearer(
    "http://localhost:9000/authorize",
    "http://localhost:9000/api/token",
    scopes={"openid": "openid", "offline_access": "offline_access"},
)

auth = FiefAuth(fief, scheme)

app = FastAPI()

origins = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://192.168.1.108:5173",
    "http://localhost:7000",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:9000",
    "http://localhost:9000"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth_test")


class BasicResponse(BaseModel):
    response_text: str


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def fake_decode_token(token, db: Session = Depends(get_db)):
    return crud.get_user_by_username(db=db, user_name=token)


@app.get("/ping/", response_model=BasicResponse)
def ping():
    time = datetime.utcnow()
    return {"response_text": str(time)}


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
    token: str = Depends(oauth2_scheme),
):
    token_data = authenticate_user(token=token, db=db)
    user_id = crud.convert_user_name_to_user_id(db=db, user_name=token_data.username)

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


@app.post("/auth_test/")
def auth_test(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    db_user = crud.get_user_by_username(db=db, user_name=form_data.username)
    if db_user is None:
        raise HTTPException(status_code=401, detail="Username incorrect")
    if not crud.verify_password(
        password=form_data.password,
        hashed_password=crud.get_user_hashed_password(
            db=db, user_name=form_data.username
        ),
        db=db,
    ):
        raise HTTPException(status_code=401, detail="Password incorrect.")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": form_data.username}, expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer"}


def authenticate_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token=token, key=SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = schemas.TokenData(username=username)
    except JWTError:
        raise credentials_exception

    user = crud.get_user_by_username(db=db, user_name=token_data.username)

    if user is None:
        raise credentials_exception
    else:
        return token_data


@app.get("/users/me/", response_model=schemas.User)
def read_users_me(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    token_data = authenticate_user(token=token, db=db)
    user = crud.get_user_by_username(db=db, user_name=token_data.username)
    return user


@app.get("/users/me/my_messages/received", response_model=list[schemas.Message])
def read_users_me_messages_received(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
):
    token_data = authenticate_user(token=token, db=db)
    received_messages = crud.get_user_received_messages(
        db=db,
        user_id=crud.convert_user_name_to_user_id(db=db, user_name=token_data.username),
    )
    return received_messages


@app.get("/users/me/my_messages/sent", response_model=list[schemas.Message])
def read_users_me_messages_sent(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
):
    token_data = authenticate_user(token=token, db=db)
    sent_messages = crud.get_user_sent_messages(
        db=db,
        user_id=crud.convert_user_name_to_user_id(db=db, user_name=token_data.username),
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
