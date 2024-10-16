from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from concurrent.futures import ThreadPoolExecutor
import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, TimeoutException
import asyncio
import re

# 최대 8개의 쓰레드를 사용하여 동시 요청 처리
executor = ThreadPoolExecutor(max_workers=8)

def loadReceipt(arg1, client_ip, user_agent):
    # 크롬 드라이버를 설정합니다.
    options = webdriver.ChromeOptions()
    options.add_argument("headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=options)

    # 대상 웹사이트로 이동합니다.
    url = f'https://report.sunmoon.ac.kr/ReportingServer/ses_viewer.jsp?path=sws&param1={arg1}&param2=2024&param3=21&param4=01&pgm=edupay_report_etc.mrd'
    driver.get(url)

    try:
        # WebDriverWait을 사용하여 특정 요소가 로드될 때까지 최대 10초 대기
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        wait = WebDriverWait(driver, 10)

        # 페이지가 정상적으로 로드되었는지 확인하기 위한 주요 제목 찾기
        try:
            main_title = wait.until(EC.presence_of_element_located(
                (By.XPATH, "//div[contains(text(), '교 육 비 납 입 증 명 서')]")))
        except TimeoutException:
            # 주요 제목이 없으면 페이지가 정상적으로 로드되지 않은 것으로 간주
            raise Exception("페이지가 정상적으로 로드되지 않았습니다.")

        # 레이블과 값을 매핑하기 위한 딕셔너리 (필요한 레이블만 포함)
        labels = {
            "학번": "stnum",
            "학생회비": "student_fee"
        }

        temp_data = {}
        for label, key in labels.items():
            try:
                # 정확히 레이블 텍스트와 일치하는 div를 찾기
                label_element = wait.until(EC.presence_of_element_located(
                    (By.XPATH, f"//div[text()='{label}']")))
                if key == "student_fee":
                    # 학생회비는 레이블로부터 9개의 div 뒤에 위치
                    value_element = label_element
                    for _ in range(9):
                        value_element = value_element.find_element(By.XPATH, "following-sibling::div[1]")
                    value_text = value_element.text.strip()
                else:
                    # 다른 필드는 바로 다음 형제 div에서 값을 찾기
                    value_element = label_element.find_element(By.XPATH, "following-sibling::div[1]")
                    value_text = value_element.text.strip()

                # 데이터 검증 및 저장
                if key == "stnum":
                    # 학번이 숫자 10자리인지 확인
                    if re.fullmatch(r'\d{10}', value_text):
                        temp_data[key] = value_text
                    else:
                        temp_data[key] = "정보 조회를 실패했습니다"
                elif key == "student_fee":
                    # 학생회비가 숫자인지 확인
                    if re.fullmatch(r'\d{1,3}(,\d{3})*', value_text):
                        temp_data[key] = value_text
                    else:
                        temp_data[key] = "정보 조회를 실패했습니다"
                else:
                    # 기타 필드는 단순히 비어있는지 확인
                    if value_text:
                        temp_data[key] = value_text
                    else:
                        temp_data[key] = "정보 조회를 실패했습니다"

            except (NoSuchElementException, TimeoutException) as e:
                temp_data[key] = "정보 조회를 실패했습니다"
                print(f"Error extracting {key}: {str(e)}")

        # 대상학생 섹션에서 성명 추출
        try:
            # "대상학생" 레이블 찾기
            target_student_label = wait.until(EC.presence_of_element_located(
                (By.XPATH, "//div[contains(text(), '대상학생')]")))
            # "대상학생" 레이블의 위치를 기준으로 "성명" 찾기
            name_label_element = target_student_label.find_element(By.XPATH, "following-sibling::div[contains(text(), '성명')]")
            name_value_element = name_label_element.find_element(By.XPATH, "following-sibling::div[1]")
            name_text = name_value_element.text.strip()
            if name_text and name_text != "주민등록번호":
                temp_data["name"] = name_text
            else:
                temp_data["name"] = "정보 조회를 실패했습니다"
        except (NoSuchElementException, TimeoutException) as e:
            temp_data["name"] = "정보 조회를 실패했습니다"
            print(f"Error extracting name: {str(e)}")

        # 학과/학기 필드에 학과명과 학기가 포함된 경우 분리
        try:
            depart_semester_element = wait.until(EC.presence_of_element_located(
                (By.XPATH, "//div[text()='학과/학기']")))
            depart_semester_text = depart_semester_element.find_element(By.XPATH, "following-sibling::div[1]").text.strip()
            if depart_semester_text:
                parts = depart_semester_text.split("/")
                if len(parts) == 2:
                    depart = parts[0].strip()
                    semester = parts[1].strip()
                else:
                    depart = depart_semester_text.strip()
                    semester = ""
            else:
                depart = "정보 조회를 실패했습니다"
                semester = ""
        except (NoSuchElementException, TimeoutException) as e:
            depart = "정보 조회를 실패했습니다"
            semester = ""
            print(f"Error extracting depart_semester: {str(e)}")

        # 학과가 비어있거나 유효하지 않으면 "정보 조회를 실패했습니다"
        if not depart:
            depart = "정보 조회를 실패했습니다"

        # 학비 납부 여부 체크 (예시: 학생회비 >= 20000)
        try:
            student_fee_clean = temp_data.get("student_fee", "0").replace(",", "")
            student_fee = int(student_fee_clean)
            check = student_fee >= 20000
        except ValueError:
            check = False
            print("Error converting student_fee to integer.")

        # `result_data` 딕셔너리를 `check`를 먼저 추가하여 생성
        result_data = {
            "check": check,
            "stnum": temp_data.get("stnum", "정보 조회를 실패했습니다"),
            "name": temp_data.get("name", "정보 조회를 실패했습니다"),
            "depart": depart
            # "semester": semester  # 필요 시 포함 가능
        }

        # 추가 데이터 검증: 모든 필드가 "정보 조회를 실패했습니다"인 경우
        if all(value == "정보 조회를 실패했습니다" for key, value in result_data.items() if key != "check"):
            raise Exception("모든 필드 정보 조회에 실패했습니다.")

        # 조건에 맞는 경우 로그 기록 (student_fee와 semester 제외)
        if result_data.get("check") and result_data.get("depart") in [
            "AI소프트웨어학과", "컴퓨터공학부", "미래자동차공학부", "스마트자동차공학부"]:
            with open("log.txt", "a", encoding="utf-8") as f:
                current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                log_entry = f"{current_time} | IP: {client_ip} | User-Agent: {user_agent} | {result_data}\n"
                f.write(log_entry)

    except Exception as e:
        # 에러 발생 시 로그에 기록
        with open("error_log.txt", "a", encoding="utf-8") as f:
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_entry = f"{current_time} | IP: {client_ip} | User-Agent: {user_agent} | Error: {str(e)}\n"
            f.write(log_entry)
    finally:
        # 드라이버를 종료합니다.
        driver.quit()

    return result_data

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

# 비동기 함수로 만들어주기 위해 ThreadPoolExecutor를 사용하여 loadReceipt를 병렬로 처리
async def loadReceipt_async(arg1, client_ip, user_agent):
    loop = asyncio.get_event_loop()
    result_data = await loop.run_in_executor(executor, loadReceipt, arg1, client_ip, user_agent)
    return result_data

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request, name="index.html", context={}
    )

@app.post("/result", response_class=HTMLResponse)
async def result(request: Request, stnum: str = Form(...)):
    # 클라이언트 IP 추출 (프록시를 고려한 방법)
    client_ip = request.headers.get('x-forwarded-for')
    if client_ip:
        client_ip = client_ip.split(",")[0].strip()
    else:
        client_ip = request.client.host

    # User-Agent 추출
    user_agent = request.headers.get('user-agent', 'unknown')

    # 비동기적으로 loadReceipt 호출
    result_data = await loadReceipt_async(stnum, client_ip, user_agent)
    print(result_data)
    return templates.TemplateResponse(
        "result.html", {"request": request, **result_data}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=80)
