from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from typing import Optional
import asyncpg
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta

# --- Конфигурация ---
DATABASE_URL = "postgresql://postgres:779058asb@localhost/p2p_lending"
SECRET_KEY = "your-secret-key-change-it"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

app = FastAPI(title="P2P Lending API")
app.mount("/static", StaticFiles(directory="static", html=True), name="static")

# --- Подключение к БД ---
async def get_db():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        await conn.close()

# --- Модели Pydantic ---
class UserCreate(BaseModel):
    full_name: str
    email: EmailStr
    phone: str
    password: str
    role: str = "borrower"

class LoanRequestCreate(BaseModel):
    amount: float
    term_months: int
    interest_rate: float
    purpose: Optional[str] = None

class InvestmentCreate(BaseModel):
    loan_request_id: int
    amount: float

# --- Вспомогательные функции ---
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme), conn=Depends(get_db)):
    credentials_exception = HTTPException(status_code=401, detail="Could not validate credentials")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_str = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
        user_id = int(user_id_str)  # преобразуем строку в целое число
    except (JWTError, ValueError):
        raise credentials_exception
    user = await conn.fetchrow("SELECT id, full_name, email, role, balance, rating FROM users WHERE id = $1", user_id)
    if not user:
        raise credentials_exception
    return dict(user)

# --- Эндпоинты ---
@app.get("/")
async def root():
    return RedirectResponse(url="/static/index.html")
@app.post("/register")
async def register(user: UserCreate, conn=Depends(get_db)):
    existing = await conn.fetchrow("SELECT id FROM users WHERE email = $1", user.email)
    if existing:
        raise HTTPException(400, "Email already registered")
    hashed = hash_password(user.password)
    role_upper = user.role.upper()
    if role_upper not in ('BORROWER', 'INVESTOR', 'ADMIN'):
        raise HTTPException(400, "Invalid role")
    try:
        result = await conn.fetchrow(
            "INSERT INTO users (full_name, email, phone, password_hash, role, balance, rating) VALUES ($1, $2, $3, $4, $5, 0, 0) RETURNING id",
            user.full_name, user.email, user.phone, hashed, role_upper
        )
        return {"id": result["id"], "message": "User created"}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), conn=Depends(get_db)):
    user = await conn.fetchrow("SELECT id, password_hash FROM users WHERE email = $1", form_data.username)
    if not user or not verify_password(form_data.password, user["password_hash"]):
        raise HTTPException(401, "Incorrect email or password")
    token = create_access_token(data={"sub": str(user["id"])})
    return {"access_token": token, "token_type": "bearer"}

@app.get("/me")
async def get_me(current_user = Depends(get_current_user)):
    return current_user

@app.post("/loan-requests")
async def create_loan_request(loan: LoanRequestCreate, current_user = Depends(get_current_user), conn=Depends(get_db)):
    if current_user["role"] != "BORROWER":
        raise HTTPException(403, "Only borrowers can create loan requests")
    result = await conn.fetchrow(
        "INSERT INTO loan_requests (borrower_id, amount, term_months, interest_rate, purpose, status, created_at) VALUES ($1, $2, $3, $4, $5, 'pending', CURRENT_DATE) RETURNING id",
        current_user["id"], loan.amount, loan.term_months, loan.interest_rate, loan.purpose
    )
    return {"id": result["id"], "message": "Loan request created"}

@app.get("/loan-requests/open")
async def get_open_loan_requests(conn=Depends(get_db)):
    rows = await conn.fetch("SELECT lr.*, u.full_name as borrower_name FROM loan_requests lr JOIN users u ON lr.borrower_id = u.id WHERE lr.status = 'pending'")
    return [dict(r) for r in rows]

@app.post("/investments")
async def invest(inv: InvestmentCreate, current_user = Depends(get_current_user), conn=Depends(get_db)):
    if current_user["role"] not in ("INVESTOR", "ADMIN"):
        raise HTTPException(403, "Only investors can invest")
    loan = await conn.fetchrow("SELECT amount, status FROM loan_requests WHERE id = $1", inv.loan_request_id)
    if not loan:
        raise HTTPException(404, "Loan request not found")
    if loan["status"] != "pending":
        raise HTTPException(400, "Loan not open for investment")
    invested_sum = await conn.fetchval("SELECT COALESCE(SUM(amount), 0) FROM investments WHERE loan_request_id = $1", inv.loan_request_id)
    remaining = loan["amount"] - invested_sum
    if inv.amount > remaining:
        raise HTTPException(400, f"Amount exceeds remaining need ({remaining})")
    await conn.execute(
        "INSERT INTO investments (investor_id, loan_request_id, amount, invested_at) VALUES ($1, $2, $3, CURRENT_DATE)",
        current_user["id"], inv.loan_request_id, inv.amount
    )
    if remaining - inv.amount <= 0:
        await conn.execute("UPDATE loan_requests SET status = 'funded' WHERE id = $1", inv.loan_request_id)
    return {"message": "Investment successful"}

@app.get("/investments/my")
async def my_investments(current_user = Depends(get_current_user), conn=Depends(get_db)):
    rows = await conn.fetch(
        "SELECT i.*, lr.amount as loan_amount, lr.interest_rate FROM investments i JOIN loan_requests lr ON i.loan_request_id = lr.id WHERE i.investor_id = $1",
        current_user["id"]
    )
    return [dict(r) for r in rows]

@app.get("/reports/active-loans")
async def active_loans(conn=Depends(get_db)):
    rows = await conn.fetch("SELECT * FROM loan_requests WHERE status = 'funded'")
    return [dict(r) for r in rows]