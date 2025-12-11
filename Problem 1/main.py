from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from enum import Enum
from typing import Optional
from datetime import datetime
import jwt
import os
import uvicorn
import psycopg2
from psycopg2.extras import RealDictCursor

app = FastAPI()
security = HTTPBearer()

# ==================== Database Connection ====================
def get_db_connection():
    conn = psycopg2.connect(
        host="localhost",
        database="Court_system",
        user="postgres_1",
        password="postgres",
        port="5432"
    )
    return conn

# ==================== Enums ====================
class UserRole(str, Enum):
    DEFENDANT = "defendant"
    PLAINTIFF = "plaintiff"
    JUROR = "juror"
    JUDGE = "judge"

class VerdictStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class Vote(str, Enum):
    GUILTY = "guilty"
    NOT_GUILTY = "not_guilty"

# ==================== Pydantic Models ====================
class SignupRequest(BaseModel):
    username: str
    password: str
    role: UserRole

class LoginRequest(BaseModel):
    username: str
    password: str

class CaseSubmission(BaseModel):
    defendant_name: str
    plaintiff_name: str
    argument: str
    evidence: str

class VoteRequest(BaseModel):
    verdict: Vote

class CaseUpdate(BaseModel):
    argument: Optional[str] = None
    evidence: Optional[str] = None

# ==================== Utility Functions ====================
def create_token(username: str) -> str:
    return jwt.encode({"username": username}, "secret_key", algorithm="HS256")

def verify_token(credentials: HTTPAuthorizationCredentials) -> str:
    try:
        payload = jwt.decode(credentials.credentials, "secret_key", algorithms=["HS256"])
        username = payload.get("username")
        if not username:
            raise HTTPException(status_code=401, detail="Token does not contain username")
        return username
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Token verification failed: {str(e)}")

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    return verify_token(credentials)

# ==================== Auth Routes ====================
@app.post("/auth/signup")
def signup(request: SignupRequest):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT username FROM users WHERE username = %s", (request.username,))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="User already exists")
        
        cur.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
               (request.username, request.password, request.role.value))
        conn.commit()
        return {"message": "User registered", "token": create_token(request.username)}
    finally:
        cur.close()
        conn.close()

@app.post("/auth/login")
def login(request: LoginRequest):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT password FROM users WHERE username = %s", (request.username,))
        user = cur.fetchone()
        if not user or user["password"] != request.password:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return {"token": create_token(request.username)}
    finally:
        cur.close()
        conn.close()

# ==================== Case Routes ====================
@app.post("/case/submit")
def submit_case(case: CaseSubmission, username: str = Depends(get_current_user)):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT role FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        if user["role"] not in ["defendant", "plaintiff"]:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        cur.execute("""INSERT INTO cases (defendant_name, plaintiff_name, argument, evidence, status, submitted_by, created_at)
                      VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                   (case.defendant_name, case.plaintiff_name, case.argument, case.evidence,
                          "pending", username, datetime.now()))
        case_id = cur.fetchone()["id"]
        conn.commit()
        return {"case_id": case_id, "status": "pending"}
    
    finally:
        cur.close()
        conn.close()

@app.get("/case/all")
def get_all_cases(username: str = Depends(get_current_user)):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT * FROM cases")
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()

@app.get("/case/by-name/{name}")
def filter_by_name(name: str, username: str = Depends(get_current_user)):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT role FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        if user["role"] != "juror":
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        cur.execute("""SELECT * FROM cases WHERE LOWER(defendant_name) LIKE %s OR LOWER(plaintiff_name) LIKE %s""",
                   (f"%{name.lower()}%", f"%{name.lower()}%"))
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()

@app.patch("/case/edit/{case_id}")
def edit_case(case_id: int, update: CaseUpdate, username: str = Depends(get_current_user)):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT role FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        if user[0] != "judge":
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        cur.execute("SELECT id FROM cases WHERE id = %s", (case_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Case not found")
        
        if update.argument:
            cur.execute("UPDATE cases SET argument = %s WHERE id = %s", (update.argument, case_id))
        if update.evidence:
            cur.execute("UPDATE cases SET evidence = %s WHERE id = %s", (update.evidence, case_id))
        conn.commit()
        
        cur.execute("SELECT * FROM cases WHERE id = %s", (case_id,))
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()

@app.delete("/case/delete/{case_id}")
def delete_case(case_id: int, username: str = Depends(get_current_user)):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT role FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        if user[0] != "judge":
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        cur.execute("SELECT id FROM cases WHERE id = %s", (case_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Case not found")
        
        cur.execute("DELETE FROM cases WHERE id = %s", (case_id,))
        conn.commit()
        return {"message": "Case deleted"}
    finally:
        cur.close()
        conn.close()

@app.patch("/case/approve/{case_id}")
def approve_case(case_id: int, username: str = Depends(get_current_user)):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT role FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        if user["role"] != "judge":
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        cur.execute("UPDATE cases SET status = %s WHERE id = %s RETURNING *",
                   ("approved", case_id))
        case = cur.fetchone()
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        conn.commit()
        return case
    finally:
        cur.close()
        conn.close()

@app.patch("/case/reject/{case_id}")
def reject_case(case_id: int, username: str = Depends(get_current_user)):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT role FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        if user["role"] != "judge":
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        cur.execute("UPDATE cases SET status = %s WHERE id = %s RETURNING *",
                   ("rejected", case_id))
        case = cur.fetchone()
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        conn.commit()
        return case
    finally:
        cur.close()
        conn.close()

# ==================== Jury Routes ====================
@app.post("/jury/vote/{case_id}")
def vote(case_id: int, vote_req: VoteRequest, username: str = Depends(get_current_user)):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT role FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        if user[0] != "juror":
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        cur.execute("SELECT id FROM cases WHERE id = %s", (case_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Case not found")
        
        cur.execute("SELECT id FROM votes WHERE case_id = %s AND juror = %s", (case_id, username))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="Already voted")
        
        cur.execute("INSERT INTO votes (case_id, juror, verdict) VALUES (%s, %s, %s)",
             (case_id, username, vote_req.verdict.value))
        conn.commit()
        return {"message": "Vote recorded"}
    finally:
        cur.close()
        conn.close()

@app.get("/jury/results/{case_id}")
def get_results(case_id: int, username: str = Depends(get_current_user)):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT id FROM cases WHERE id = %s", (case_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Case not found")
        
        cur.execute("""SELECT COUNT(*) as count, verdict FROM votes WHERE case_id = %s GROUP BY verdict""",
                   (case_id,))
        results = cur.fetchall()
        
        guilty_count = next((r["count"] for r in results if r["verdict"] == "guilty"), 0)
        not_guilty_count = next((r["count"] for r in results if r["verdict"] == "not_guilty"), 0)
        
        return {"guilty": guilty_count, "not_guilty": not_guilty_count, "total_votes": guilty_count + not_guilty_count}
    finally:
        cur.close()
        conn.close()

