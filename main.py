from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import pymysql
import os
import logging
from datetime import datetime

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# 정적 파일 제공 설정
app.mount("/static", StaticFiles(directory="static"), name="static")

# 데이터베이스 연결 설정
DATABASE_CONFIG = {
    'host': os.getenv('DATABASE_HOST'),
    'port': int(os.getenv('DATABASE_PORT')),
    'user': os.getenv('DATABASE_USER'),
    'password': os.getenv('DATABASE_PASSWORD'),
    'db': os.getenv('DATABASE_NAME')
}

def get_db_connection():
    return pymysql.connect(**DATABASE_CONFIG)

def loadReceipt(student_id, client_ip, user_agent, name):
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT name, department FROM students WHERE student_id = %s", (student_id,))
            student = cursor.fetchone()

            cursor.execute("SELECT fee_paid FROM registration_info WHERE student_id = %s", (student_id,))
            registration = cursor.fetchone()

            if student and registration:
                if student["name"] == name:
                    return {
                        "name": student["name"],
                        "stnum": student_id,
                        "depart": student["department"],
                        "check": registration["fee_paid"] == 1
                    }
                else:
                    return {
                        "name": "일치하는 학생이 없습니다",
                        "stnum": "일치하는 학생이 없습니다",
                        "depart": "일치하는 학생이 없습니다",
                        "check": False
                    }
            else:
                return {
                    "name": "일치하는 학생이 없습니다",
                    "stnum": "일치하는 학생이 없습니다",
                    "depart": "일치하는 학생이 없습니다",
                    "check": False
                }
    finally:
        conn.close()

# 로그 설정
logging.basicConfig(level=logging.INFO)
success_logger = logging.getLogger("success_logger")
error_logger = logging.getLogger("error_logger")

success_handler = logging.FileHandler("log.txt")
error_handler = logging.FileHandler("error_log.txt")

success_logger.addHandler(success_handler)
error_logger.addHandler(error_handler)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request, name="index.html", context={}
    )

@app.post("/result", response_class=HTMLResponse)
async def result(request: Request, stnum: str = Form(...), name: str = Form(...)):
    # 클라이언트 IP 추출 (프록시를 고려한 방법)
    client_ip = request.headers.get('x-forwarded-for')
    if client_ip:
        client_ip = client_ip.split(",")[0].strip()
    else:
        client_ip = request.client.host

    # User-Agent 추출
    user_agent = request.headers.get('user-agent', 'unknown')

    try:
        # 동기적으로 loadReceipt 호출
        result_data = loadReceipt(stnum, client_ip, user_agent, name)
        log_message = f"{datetime.now()} | IP: {client_ip} | User-Agent: {user_agent} | {result_data}"
        
        if result_data["name"] == "일치하는 학생이 없습니다":
            error_logger.error(log_message)
        else:
            success_logger.info(log_message)
    except Exception as e:
        log_message = f"{datetime.now()} | IP: {client_ip} | User-Agent: {user_agent} | Error: {str(e)}"
        error_logger.error(log_message)
        result_data = {
            "check": False,
            "stnum": "일치하는 학생이 없습니다",
            "name": "일치하는 학생이 없습니다",
            "depart": "일치하는 학생이 없습니다"
        }

    print(result_data)
    return templates.TemplateResponse(
        "result.html", {"request": request, **result_data}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=80)