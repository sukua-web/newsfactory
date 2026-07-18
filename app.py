import streamlit as st
import os
import requests
import json
import random
import re
import time
import smtplib
from email.mime.text import MIMEText
from email.message import EmailMessage
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import google.generativeai as genai
from serpapi import GoogleSearch

# --- 세션 상태 초기화 ---
if "generated_images" not in st.session_state:
    st.session_state.generated_images = []

# 1. 페이지 설정
st.set_page_config(page_title="AI 인스타 카드뉴스 공장", page_icon="🎨", layout="centered")
st.title("🎨 AI 인스타 카드뉴스 공장 (최종 완성본)")

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
        except: 
            return None
    return font_path

font_path = load_assets()
user_topic = st.text_input("✍️ 제작하고 싶은 카드뉴스 주제를 입력하세요")

# 4. 이미지 검색 함수
def fetch_serpapi_image(query, api_key):
    try:
        params = {"engine": "google_images", "q": query, "api_key": api_key, "ijn": "0"}
        search = GoogleSearch(params)
        results = search.get_dict()
        
        if "images_results" in results:
            for img_data in results["images_results"][:5]:
                img_url = img_data.get("original")
                if not img_url: continue
                try:
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    img_response = requests.get(img_url, headers=headers, timeout=5)
                    if img_response.status_code == 200:
                        img_content = BytesIO(img_response.content)
                        return Image.open(img_content).convert("RGB")
                except Exception:
                    continue
    except Exception:
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
        if os.path.exists(img_path):
            with open(img_path, 'rb') as f:
                img_data = f.read()
                msg.add_attachment(img_data, maintype='image', subtype='png', filename=img_path)

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(sender_email, app_password)
        smtp.send_message(msg)

# =====================================================================
# 6. 실행 로직 (카드뉴스 생성 파트)
# =====================================================================
if st.button("🚀 카드뉴스 5장 생성하기"):
    if not gemini_key or not user_topic:
        st.warning("API 키와 주제를 확인하세요.")
    else:
        with st.spinner("AI가 작업 중입니다..."):
            
            # 잘 쓰시던 모델명 리스트 그대로 유지 및 안전장치 적용
            models_to_try = ['gemini-2.0-flash', 'gemini-2.0-flash-lite', 'gemini-1.5-flash']
            model = None
            is_model_ready = False 
            
            for m_name in models_to_try:
                try:
                    temp_model = genai.GenerativeModel(m_name)
                    temp_model.generate_content("Hi", generation_config={"max_output_tokens": 5})
                    st.toast(f"✅ 모델 연결 성공: {m_name}")
                    
                    model = temp_model
                    is_model_ready = True
                    break 
                except Exception:
                    continue
            
            if not is_model_ready:
                st.error("⚠️ 현재 API 서버 응답이 지연되거나 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")
                st.stop()

            prompt = f"주제: '{user_topic}'\n인스타그램 카드뉴스 5장 기획. JSON 배열로 출력. 키: slide_num, main_en, sub_ko, sub_ja, search_keyword."
            response = model.generate_content(prompt)
            raw_text = response.text.replace("```json", "").replace("```", "").strip()

            match = re.search(r'\[.*\]', raw_text, re.DOTALL)
            json_text = match.group() if match else raw_text

            try:
                slides_data = json.loads(json_text)
            except json.JSONDecodeError:
                st.error("AI가 올바른 형식의 데이터를 주지 않았습니다. 다시 시도해주세요.")
                st.stop()
            
            width, height = 1080, 1350
            font_en = ImageFont.truetype(font_path, 90)
            font_ko = ImageFont.truetype(font_path, 45)
            font_ja = ImageFont.truetype(font_path, 35)
            
            temp_images = []
            
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
                temp_images.append((fname, bg))
            
            st.session_state.generated_images = temp_images
            st.success("✅ 카드뉴스 5장 생성 완료!")


# =====================================================================
# 7. 화면 출력 및 이메일 전송 파트 (독립된 영역)
# =====================================================================
if st.session_state.generated_images:
    st.divider()
    
    # 1) 이미지 화면 출력 & 개별 다운로드 버튼
    cols = st.columns(5)
    for i, (fname, img) in enumerate(st.session_state.generated_images):
        with cols[i]:
            st.image(img, use_container_width=True)
            with open(fname, "rb") as f: 
                st.download_button("💾 다운", f, fname, key=f"dl_{i}")
    
    # 2) 이메일 전송 UI
    st.divider()
    st.subheader("✉️ 완성된 카드뉴스 내 이메일로 받기")
    
    if "GMAIL_USER" not in st.secrets or "GMAIL_PASS" not in st.secrets:
        st.error("⚠️ `.streamlit/secrets.toml` 설정이 누락되었습니다.")
    else:
        target_email = st.secrets["GMAIL_USER"]
        st.info(f"📬 설정된 계정({target_email})으로 발송됩니다.")
        
        if st.button("📤 내 이메일로 바로 전송하기"):
            with st.spinner("메일 발송 중..."):
                try:
                    file_names = [item[0] for item in st.session_state.generated_images]
                    send_email_with_images(
                        sender_email=st.secrets["GMAIL_USER"],
                        app_password=st.secrets["GMAIL_PASS"].replace(" ", ""),
                        receiver_email=st.secrets["GMAIL_USER"],
                        subject=f"[카드뉴스] '{user_topic}' 카드뉴스 발송",
                        image_files=file_names
                    )
                    st.success("✅ 메일 발송 완료! 이메일함을 확인해주세요.")
                except Exception as e:
                    st.error(f"메일 발송 오류 발생: {e}")