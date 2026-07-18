import streamlit as st
import os
import requests
import json
import random
import re
import time
import smtplib
import smtplib
from email.mime.text import MIMEText
from email.message import EmailMessage
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import google.generativeai as genai
from serpapi import GoogleSearch
# 만약 위 코드가 계속 에러가 난다면 아래 방식으로 바꿔보세요:
# import serpapi
# client = serpapi.Client(api_key="내_API_KEY")

# 1. 페이지 설정
st.set_page_config(page_title="AI 인스타 카드뉴스 공장", page_icon="🎨", layout="centered")

st.title("🎨 AI 인스타 카드뉴스 공장 (v3.5 - Secrets 자동 로그인)")

# 2. API 키 설정 (Sidebar)
st.sidebar.header("🔑 API 키 설정")
env_gemini = os.environ.get("GEMINI_API_KEY", "")
env_serpapi = os.environ.get("SERPAPI_KEY", "")

gemini_key = env_gemini if env_gemini else st.sidebar.text_input("Gemini API Key", type="password")
serpapi_key = env_serpapi if env_serpapi else st.sidebar.text_input("SerpApi Key", type="password")

if gemini_key:
    genai.configure(api_key=gemini_key)

# 3. 폰트 로드
@st.cache_resource
def load_assets():
    font_url = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Korean/NotoSansCJKkr-Bold.otf"
    font_path = "CustomFont.otf"
    if not os.path.exists(font_path):
        try:
            with open(font_path, "wb") as f:
                f.write(requests.get(font_url, timeout=15).content)
        except: return None
    return font_path

font_path = load_assets()
user_topic = st.text_input("✍️ 제작하고 싶은 카드뉴스 주제를 입력하세요")

# 4. 이미지 검색 함수 (SerpApi 사용 - 효율 극대화)
def fetch_serpapi_image(query, api_key):
    try:
        params = {
            "engine": "google_images",
            "q": query,
            "api_key": api_key,
            "ijn": "0"
        }
        search = GoogleSearch(params)
        results = search.get_dict()
        
        if "images_results" in results:
            for img_data in results["images_results"][:5]:
                img_url = img_data.get("original")
                if not img_url:
                    continue
                    
                try:
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    img_response = requests.get(img_url, headers=headers, timeout=5)
                    
                    if img_response.status_code == 200:
                        img_content = BytesIO(img_response.content)
                        return Image.open(img_content).convert("RGB")
                except Exception:
                    continue
                    
    except Exception as e:
        return None
    return None

# 5. 스마트 그리기 헬퍼 함수들
def smart_wrap_text(text, font, max_width, draw):
    lines = []
    paragraphs = str(text).split('\n')
    
    for paragraph in paragraphs:
        words = paragraph.split(' ')
        current_line = ""
        
        for word in words:
            if draw.textbbox((0, 0), word, font=font)[2] > max_width:
                if current_line:
                    lines.append(current_line)
                    current_line = ""
                for char in word:
                    test_line = current_line + char
                    if draw.textbbox((0, 0), test_line, font=font)[2] <= max_width:
                        current_line = test_line
                    else:
                        if current_line: lines.append(current_line)
                        current_line = char
            else:
                test_line = f"{current_line} {word}".strip() if current_line else word
                if draw.textbbox((0, 0), test_line, font=font)[2] <= max_width:
                    current_line = test_line
                else:
                    lines.append(current_line)
                    current_line = word
        
        if current_line:
            lines.append(current_line)
            
    return lines

def draw_smart_text_with_outline(draw, position, text, font, text_color, outline_color, max_width, outline_width=2, line_spacing=15):
    lines = smart_wrap_text(text, font, max_width, draw)
    line_heights = [draw.textbbox((0,0), line, font=font)[3] - draw.textbbox((0,0), line, font=font)[1] for line in lines]
    total_height = sum(line_heights) + line_spacing * (len(lines) - 1)
    current_y = position[1] - total_height // 2
    
    for line, h in zip(lines, line_heights):
        x, y = position[0], current_y + h // 2
        for dx in range(-outline_width, outline_width+1):
            for dy in range(-outline_width, outline_width+1):
                draw.text((x+dx, y+dy), line, fill=outline_color, font=font, anchor="mm", align="center")
        draw.text((x, y), line, fill=text_color, font=font, anchor="mm", align="center")
        current_y += h + line_spacing

# 5.5 이메일 발송 헬퍼 함수
def send_email_with_images(sender_email, app_password, receiver_email, subject, image_files):
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg.set_content("AI가 생성한 카드뉴스 이미지가 첨부되었습니다.\n\n- AI 인스타 카드뉴스 공장")

    for img_path in image_files:
        with open(img_path, 'rb') as f:
            img_data = f.read()
            msg.add_attachment(img_data, maintype='image', subtype='png', filename=img_path)

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(sender_email, app_password)
        smtp.send_message(msg)

# 6. 실행 로직
if st.button("🚀 카드뉴스 5장 생성하기"):
    if not gemini_key or not user_topic:
        st.warning("API 키와 주제를 확인하세요.")
    else:
        with st.spinner("AI가 작업 중입니다..."):
            models_to_try = ['gemini-2.0-flash', 'gemini-2.0-flash-lite', 'gemini-3.1-flash-lite', 'gemini-3.5-flash', 'gemini-1.5-flash']
            model = None
            
            for m_name in models_to_try:
                try:
                    model = genai.GenerativeModel(m_name)
                    model.generate_content("Hi", generation_config={"max_output_tokens": 5})
                    st.toast(f"✅ 모델 연결 성공: {m_name}")
                    break 
                except Exception as e:
                    continue
            
            if not model:
                st.error("연결 가능한 모델을 찾지 못했습니다. API 키 권한이나 모델명을 확인해주세요.")
                st.stop()

            prompt = f"주제: '{user_topic}'\n인스타그램 카드뉴스 5장 기획. JSON 배열로 출력. 키: slide_num, main_en, sub_ko, sub_ja, search_keyword."
            response = model.generate_content(prompt)
            
            raw_text = response.text.replace("```json", "").replace("```", "").strip()

            match = re.search(r'\[.*\]', raw_text, re.DOTALL)
            if match:
                json_text = match.group()
            else:
                json_text = raw_text

            try:
                slides_data = json.loads(json_text)
            except json.JSONDecodeError as e:
                st.error("AI가 올바른 형식의 데이터를 주지 않았습니다.")
                st.text(f"Raw Output: {raw_text}")
                st.stop()
            
            width, height = 1080, 1350
            font_en = ImageFont.truetype(font_path, 90)
            font_ko = ImageFont.truetype(font_path, 45)
            font_ja = ImageFont.truetype(font_path, 35)
            
            generated_images = []
            for idx, slide in enumerate(slides_data):
                bg = fetch_serpapi_image(slide.get("search_keyword", user_topic), serpapi_key)
                
                if not bg and slide.get("search_keyword") != user_topic:
                    time.sleep(1)
                    bg = fetch_serpapi_image(user_topic, serpapi_key)
                
                if bg:
                    bg = bg.resize((width, height), Image.Resampling.LANCZOS)
                    bg = ImageEnhance.Brightness(bg).enhance(0.4)
                    c_main, c_sub, out = "#FFFFFF", "#E5E7EB", "#000000"
                else:
                    bg = Image.new("RGB", (width, height), color=random.choice(["#FFB3BA", "#FFDFBA", "#FFFFBA", "#BAFFC9", "#BAE1FF"]))
                    c_main, c_sub, out = "#111827", "#374151", "#FFFFFF"
                
                draw = ImageDraw.Draw(bg)
                draw.rectangle([60, 60, width-60, height-60], outline=c_main, width=4)
                
                draw_smart_text_with_outline(draw, (width//2, height//3), slide.get("main_en", ""), font_en, c_main, out, max_width=width-240)
                draw_smart_text_with_outline(draw, (width//2, height//2+100), slide.get("sub_ko", ""), font_ko, c_sub, out, max_width=width-240)
                draw_smart_text_with_outline(draw, (width//2, height//2+300), slide.get("sub_ja", ""), font_ja, c_sub, out, max_width=width-240)
                
                fname = f"slide_{idx+1}.png"
                bg.save(fname)
                generated_images.append((fname, bg))
            
            st.success("완성!")
            cols = st.columns(5)
            for i, (fname, img) in enumerate(generated_images):
                with cols[i]:
                    st.image(img, use_container_width=True)
                    with open(fname, "rb") as f: 
                        st.download_button("💾 다운", f, fname, key=f"dl_{i}")
            
            # --- ✨ secrets를 활용한 원터치 이메일 전송 UI ✨ ---
            st.divider()
            st.subheader("✉️ 완성된 카드뉴스 내 이메일로 받기")
            
            if "GMAIL_USER" not in st.secrets or "GMAIL_PASS" not in st.secrets:
                st.error("⚠️ `.streamlit/secrets.toml` 설정이 누락되었습니다.")
            else:
                target_email = st.secrets["GMAIL_USER"]
                st.info(f"📬 설정된 계정({target_email})으로 발송됩니다.")
                
                if st.button("📤 내 이메일로 바로 전송하기"):
                    with st.spinner("이미지를 이메일로 전송 중..."):
                        try:
                            # 1. 파일 경로 리스트 생성
                            file_names = [fname for fname, img in generated_images]
                            
                            # 2. 이메일 발송 함수 호출
                            send_email_with_images(
                                sender_email=st.secrets["GMAIL_USER"],
                                app_password=st.secrets["GMAIL_PASS"].replace(" ", ""),
                                receiver_email=target_email,
                                subject=f"[카드뉴스 자동완성] '{user_topic}' 주제의 카드뉴스입니다.",
                                image_files=file_names
                            )
                            st.success("✅ 전송이 완료되었습니다! 메일함을 확인해 보세요.")
                        except Exception as e:
                            # 여기서 에러가 뜨면 무엇이 문제인지 정확히 알 수 있습니다.
                            st.error(f"메일 발송 실패 사유: {e}")

                # (기존 메일 전송 코드 위치에 아래 내용을 넣으세요)
