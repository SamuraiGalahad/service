from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext
from datetime import datetime, timedelta
import jwt
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base
from email_validate import validate, validate_or_fail

# Конфигурация базы данных
SQLALCHEMY_DATABASE_URL = "sqlite:///./auth.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# Модель пользователя
class User(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    role = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sessions = relationship("Session", back_populates="user")


# Модель сессии
class Session(Base):
    __tablename__ = "session"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("user.id"))
    session_token = Column(String)
    expires_at = Column(DateTime)

    user = relationship("User", back_populates="sessions")


Base.metadata.create_all(bind=engine)

# Конфигурация аутентификации и хеширования паролей
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")

# Конфигурация приложения FastAPI
app = FastAPI()


# Функции для работы с базой данных
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_user(email: str, db):
    user = db.query(User).filter(User.email == email).first()
    return user


def create_user(username: str, email: str, password: str, role: str, db):
    hashed_password = pwd_context.hash(password)
    user = User(username=username, email=email, password_hash=hashed_password, role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_session(user: User, db):
    token_expires = datetime.utcnow() + timedelta(minutes=15)
    token = jwt.encode({"sub": user.email, "exp": token_expires}, "secret_key", algorithm="HS256")
    session = Session(user_id=user.id, session_token=token.decode(), expires_at=token_expires)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_current_user(token: str = Depends(oauth2_scheme), db=Depends(get_db)):
    try:
        payload = jwt.decode(token, "secret_key", algorithms=["HS256"])
        email = payload["sub"]
        user = get_user(email, db)
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except (jwt.DecodeError, jwt.InvalidTokenError):
        raise HTTPException(status_code=401, detail="Invalid token")


# Регистрация нового пользователя c ролью
@app.post("/register_with_role")
def register_with_role(username: str, email: str, password: str, role: str, db=Depends(get_db)):
    if validate(email_address=email, check_format=True):
        raise HTTPException(status_code=403, detail="Wrong email!")

    user = get_user(email, db)

    if len(password) < 6:
        raise HTTPException(status_code=414, detail="Too short!")

    if len(username) < 1:
        raise HTTPException(status_code=414, detail="Too short!")

    if role != "user" and role != "manager":
        raise HTTPException(status_code=403, detail="Wrong role!")

    if user:
        raise HTTPException(status_code=400, detail="Username already registered")
    user = create_user(username, email, password, role, db)
    return {"message": "User registered successfully"}


# Регистрация нового пользователя упрощенная
@app.post("/register")
def register(username: str, email: str, password: str, db=Depends(get_db)):
    if validate(email_address=email, check_format=True):
        raise HTTPException(status_code=403, detail="Wrong email!")

    user = get_user(email, db)

    if user:
        raise HTTPException(status_code=400, detail="Username already registered")

    user = create_user(username, email, password, "user", db)
    return {"message": "User registered successfully"}


# Аутентификация пользователя и создание сессии
@app.post("/token")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db=Depends(get_db)):
    user = get_user(form_data.username, db)
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Invalid username or password")
    session = create_session(user, db)
    return {"access_token": session.session_token, "token_type": "bearer"}


# Получение информации о текущем пользователе
@app.get("/users/me")
def read_users_me(current_user: User = Depends(get_current_user)):
    return {"username": current_user.username, "email": current_user.email, "role": current_user.role}


# Запуск приложения
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
