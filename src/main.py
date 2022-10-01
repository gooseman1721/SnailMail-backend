from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from . import crud, models, schemas
from .database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.post("/users/", response_model=schemas.User)
def create_user(user:schemas.UserCreate, db: Session = Depends(get_db)):
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

    return(users)


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
    print('pleple')
    return crud.get_user_received_messages(db=db, user_id=user_id)


@app.get("/users/all/", response_model=list[schemas.User])
def get_all_users(db: Session = Depends(get_db)):
    user_count = crud.get_user_count(db=db)
    users = crud.get_many_users(db=db, how_many=user_count)

    return(users)


@app.post("/messages/")
def create_message(message: schemas.MessageCreate, sender_id: int, receiver_id: int, db: Session = Depends(get_db)):
    return crud.create_message(db=db, message=message, sender_id=sender_id, receiver_id=receiver_id)


@app.post("/login/")
def user_login(user_name: str, cleartext_password: str, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_username(db=db, user_name=user_name)
    if db_user is None:
        raise HTTPException(
            status_code=401, detail="Username incorrect")
    if not crud.verify_password(password=cleartext_password, hashed_password=crud.get_user_hashed_password(db=db, user_name=user_name)):
        raise HTTPException(
            status_code=401, detail="Password incorrect.")

    else:
        return("Login attempt successful")
