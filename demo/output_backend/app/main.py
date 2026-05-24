from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from passlib.context import CryptContext
from typing import List, Optional
import sqlite3
import jwt
import time

class RegisterRequest(BaseModel):
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: int
    email: str

class UserModel:
    def __init__(self, id: int, email: str, hashed_password: str):
        self.id = id
        self.email = email
        self.hashed_password = hashed_password

def get_db_connection():
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    return conn

def create_tables():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            hashed_password TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

class AuthManager:
    def __init__(self):
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def hash_password(self, password: str) -> str:
        return self.pwd_context.hash(password)

    def verify_password(self, plain_password, hashed_password):
        return self.pwd_context.verify(plain_password, hashed_password)

    def create_access_token(self, user_id: int) -> str:
        # TODO: Use a proper secret key and expiration
        return jwt.encode({"user_id": user_id}, "SECRET_KEY", algorithm="HS256")

class UserService:
    def __init__(self):
        self.auth_manager = AuthManager()

    def register_user(self, user: RegisterRequest):
        conn = get_db_connection()
        cursor = conn.cursor()
        hashed = self.auth_manager.hash_password(user.password)
        try:
            cursor.execute("INSERT INTO users (email, hashed_password) VALUES (?, ?)", (user.email, hashed))
            conn.commit()
            return {"message": "User created successfully"}
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=400, detail="Email already registered")
        finally:
            conn.close()

    def login_user(self, request: LoginRequest):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email=?", (request.email,))
        user_row = cursor.fetchone()
        if not user_row:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if not self.auth_manager.verify_password(request.password, user_row[2]):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return {"access_token": self.auth_manager.create_access_token(user_row[0])}

    def list_users(self) -> List[UserResponse]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users")
        rows = cursor.fetchall()
        users = [UserModel(id=row[0], email=row[1], hashed_password=row[2]) for row in rows]
        return users

app = FastAPI()
user_service = UserService()

create_tables()

@app.post("/register")
async def register_user_endpoint(request: RegisterRequest):
    return user_service.register_user(request)

@app.post("/login")
async def login_user_endpoint(request: LoginRequest):
    return user_service.login_user(request)

@app.get("/users", response_model=List[UserResponse])
async def list_users_endpoint():
    return user_service.list_users()
