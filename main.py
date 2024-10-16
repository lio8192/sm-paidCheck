from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from concurrent.futures import ThreadPoolExecutor
import time
import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
import asyncio

# 최대 5개의 쓰레드를 사용하여 동시 요청 처리
executor = ThreadPoolExecutor(max_workers=8)

def loadReceipt(arg1):
    # 크롬 드라이버를 설정합니다.
    options = webdriver.ChromeOptions()
    options.add_argument("headless")

    driver = webdriver.Chrome(options=options)

    # 대상 웹사이트로 이동합니다.
    url = f'https://report.sunmoon.ac.kr/ReportingServer/ses_viewer.jsp?path=sws&param1={arg1}&param2=2024&param3=21&param4=01&pgm=edupay_report_etc.mrd'
    driver.get(url)

    # 동적 크롤링을 위해 웹 페이지가 완전히 로드될 때까지 기다립니다.
    time.sleep(2)

    # 필요한 요소를 찾고 텍스트를 불러옵니다.
    element1 = driver.find_element(By.CSS_SELECTOR, "#m2soft-crownix-text > div:nth-child(34)")
    text1 = element1.text
    if text1 == "2024-2학기":
        element1 = driver.find_element(By.CSS_SELECTOR, "#m2soft-crownix-text > div:nth-child(35)")
        text1 = element1.text
    element1_value = int(text1.replace(",", ""))

    # 학번
    element2 = driver.find_element(By.CSS_SELECTOR, "#m2soft-crownix-text > div:nth-child(14)")
    text2 = element2.text

    # 이름
    element3 = driver.find_element(By.CSS_SELECTOR, "#m2soft-crownix-text > div:nth-child(10)")
    text3 = element3.text

    # 학과
    element4 = driver.find_element(By.CSS_SELECTOR, "#m2soft-crownix-text > div:nth-child(16)")
    text4 = element4.text
    if text4 == "소득자와의 관계":
        department = "정보 조회를 실패했습니다"
    else:
        department = text4.split(" /")[0]

    if text3 == "주민등록번호":
        text3 = "정보 조회를 실패했습니다"

    if text2 == "학교명":
        text2 = "정보 조회를 실패했습니다"

    result_data = {"check": element1_value >= 20000 if "true" else "false", "stnum": text2, "name": text3, "depart": department}

    if element1_value >= 20000 and department in ["AI소프트웨어학과", "컴퓨터공학부", "미래자동차공학부", "스마트자동차공학부"]:
        with open("log.txt", "a", encoding="utf-8") as f:
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(current_time + " " + str(result_data) + "\n")

    # 드라이버를 종료합니다.
    driver.quit()

    return result_data


app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

# 비동기 함수로 만들어주기 위해 ThreadPoolExecutor를 사용하여 loadReceipt를 병렬로 처리
async def loadReceipt_async(arg1):
    loop = asyncio.get_event_loop()
    result_data = await loop.run_in_executor(executor, loadReceipt, arg1)
    return result_data


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request, name="index.html", context={}
    )

@app.post("/result", response_class=HTMLResponse)
async def result(request: Request, stnum: str = Form(...)):
    # 비동기적으로 loadReceipt 호출
    result_data = await loadReceipt_async(stnum)
    print(result_data)
    return templates.TemplateResponse(
        "result.html", {"request": request, **result_data}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=80)