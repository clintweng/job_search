import os
import re
import smtplib
import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import quote
from email.mime.text import MIMEText
from datetime import datetime

EMAIL_TO = "clint_weng@icloud.com"

KEYWORDS = [
    "資料分析 兼職 遠端",
    "數據分析 兼職 遠端",
    "SQL 兼職 遠端",
    "Tableau 兼職 遠端",
    "Power BI 兼職 遠端",
    "AI 顧問 兼職 遠端",
    "行政助理 兼職 遠端",
    "陪讀 兼職",
    "寵物 兼職",
    "毛小孩 兼職",
    "運動按摩 兼職",
]

HEADERS = {"User-Agent": "Mozilla/5.0"}

def extract_hourly_pay(text):
    if not text:
        return None

    m = re.search(r"時薪\s*([\d,]+)(?:\s*[~～-]\s*([\d,]+))?", text)
    if m:
        return int((m.group(2) or m.group(1)).replace(",", ""))

    m = re.search(r"日薪\s*([\d,]+)(?:\s*[~～-]\s*([\d,]+))?", text)
    if m:
        return round(int((m.group(2) or m.group(1)).replace(",", "")) / 8)

    m = re.search(r"月薪\s*([\d,]+)", text)
    if m:
        return round(int(m.group(1).replace(",", "")) / 176)

    return None

def match_score(text):
    score = 0
    high_value = ["資料分析", "數據分析", "SQL", "Tableau", "Power BI", "BI", "GA4", "AI", "顧問"]
    medium_value = ["行政助理", "陪讀", "寵物", "毛小孩", "運動按摩"]

    for k in high_value:
        if k.lower() in text.lower():
            score += 10

    for k in medium_value:
        if k in text:
            score += 4

    if any(k in text for k in ["遠端", "居家", "remote", "Remote"]):
        score += 15

    if any(k in text for k in ["兼職", "接案", "part-time", "Part-time"]):
        score += 10

    return score

def crawl_104(keyword, pages=2):
    rows = []
    for page in range(1, pages + 1):
        url = f"https://www.104.com.tw/jobs/search/?keyword={quote(keyword)}&page={page}"
        html = requests.get(url, headers=HEADERS, timeout=15).text
        soup = BeautifulSoup(html, "html.parser")

        for job in soup.select("article"):
            text = job.get_text(" ", strip=True)
            a = job.select_one("a[href]")
            link = ""

            if a:
                href = a.get("href", "")
                link = "https:" + href if href.startswith("//") else href

            pay = extract_hourly_pay(text)
            if not pay:
                continue

            rows.append({
                "source": "104",
                "keyword": keyword,
                "title_text": text[:180],
                "estimated_hourly_pay": pay,
                "match_score": match_score(text),
                "url": link
            })

    return rows

def crawl_1111(keyword, pages=2):
    rows = []

    for page in range(1, pages + 1):

        url = f"https://www.1111.com.tw/search/job?ks={quote(keyword)}&page={page}"

        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=30
            )

            response.raise_for_status()
            html = response.text

        except requests.exceptions.RequestException as e:
            print(
                f"[SKIP] 1111 timeout/error: "
                f"{keyword}, page={page}, error={e}"
            )
            continue

        soup = BeautifulSoup(html, "html.parser")

        for card in soup.select("article, li, div"):

            text = card.get_text(" ", strip=True)

            if len(text) < 50:
                continue

            pay = extract_hourly_pay(text)

            if not pay:
                continue

            a = card.select_one("a[href]")
            link = ""

            if a:
                href = a.get("href", "")
                link = (
                    "https://www.1111.com.tw" + href
                    if href.startswith("/")
                    else href
                )

            rows.append({
                "source": "1111",
                "keyword": keyword,
                "title_text": text[:180],
                "estimated_hourly_pay": pay,
                "match_score": match_score(text),
                "url": link
            })

    return rows

def send_email(df):
    today = datetime.now().strftime("%Y-%m-%d")

    html = f"""
    <h2>今日兼職職缺推薦 - {today}</h2>
    <p>依照時薪高到低排序，並優先保留適合你的資料分析、BI、AI顧問、遠端兼職職缺。</p>
    """

    if df.empty:
        html += "<p>今天沒有找到符合條件的職缺。</p>"
    else:
        html += "<ol>"
        for _, row in df.head(20).iterrows():
            html += f"""
            <li>
            <b>{row['title_text']}</b><br>
            來源：{row['source']}<br>
            估算時薪：{row['estimated_hourly_pay']} 元<br>
            匹配分數：{row['match_score']}<br>
            <a href="{row['url']}">查看職缺</a>
            </li><br>
            """
        html += "</ol>"

    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = f"今日兼職職缺推薦 - {today}"
    msg["From"] = os.getenv("EMAIL_USER")
    msg["To"] = EMAIL_TO

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(os.getenv("EMAIL_USER"), os.getenv("EMAIL_PASSWORD"))
        server.send_message(msg)

def main():
    rows = []

    for keyword in KEYWORDS:
        rows += crawl_104(keyword)
        # rows += crawl_1111(keyword)

    df = pd.DataFrame(rows)

    if not df.empty:
        df = df.drop_duplicates(subset=["source", "title_text"])
        df = df[df["estimated_hourly_pay"] >= 400]
        df = df.sort_values(
            by=["match_score", "estimated_hourly_pay"],
            ascending=[False, False]
        )

    df.to_csv("part_time_jobs.csv", index=False, encoding="utf-8-sig")
    send_email(df)

if __name__ == "__main__":
    main()
