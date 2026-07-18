import streamlit as st
import os
import requests
import json
import time
import random
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import google.generativeai as genai

# 1. 페이지 설정
st.set_page_config(page_title="AI 인스타 카드뉴스 공장", page_icon="🎨", layout="centered")

st.title("🎨 AI 인스타 카드뉴스 공장 (v3.2 Stable Edition)")
st.write("주제를 입력하면 기획부터 디자인(영/한/일)까지 AI가 자동으로 완성합니다.")

# 2. API 키 설정
st.sidebar.header("🔑 API 키 설정")
env_gemini = os.environ.get("GEMINI_API_KEY", "")
env_pexels = os.environ.get("PEXELS_API_KEY", "")

gemini_key = env_gemini if env_gemini else st.sidebar.text_input("Gemini API Key를 입력하세요", type="password")
pexels_key = env_pexels if env_pexels else st.sidebar.text_input("Pexels API Key (선택)", type="password")

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
user_topic = st.text_input("✍️ 제작하고 싶은 카드뉴스 주제를 입력하세요", placeholder="예: 테슬라 FSD의 혁신적인 기술력")

# 4. 헬퍼 함수들
def wrap_text_by_word(text, font, max_width, draw, is_japanese=False):
    # 일본어는 글자 단위 처리
    if is_japanese:
        words = list(str(text))
    else:
        words = str(text).split(" ")
        
    lines = []
    current_line = ""
    
    for word in words:
        if is_japanese:
            test_line = current_line + word
        else:
            test_line = f"{current_line} {word}".strip()
            
        # 폰트 너비 계산 시 약간의 버퍼(padding)를 두어 끝에 닿지 않게 함
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current_line = test_line
        else:
            if current_line: lines.append(current_line)
            current_line = word
            
    if current_line: lines.append(current_line)
    return lines

def draw_wrapped_text_with_outline(draw, position, text, font, text_color, outline_color, max_width, outline_width=2, is_japanese=False):
    lines = wrap_text_by_word(text, font, max_width, draw, is_japanese=is_japanese)
    lines = wrap_text_by_word(text, font, max_width, draw)
    line_heights = [draw.textbbox((0,0), line, font=font)[3] - draw.textbbox((0,0), line, font=font)[1] for line in lines]
    total_height = sum(line_heights) + 15 * (len(lines) - 1)
    current_y = position[1] - total_height // 2
    for line, h in zip(lines, line_heights):
        x, y = position[0], current_y + h // 2
        for dx in range(-outline_width, outline_width+1):
            for dy in range(-outline_width, outline_width+1):
                draw.text((x+dx, y+dy), line, fill=outline_color, font=font, anchor="mm", align="center")
        draw.text((x, y), line, fill=text_color, font=font, anchor="mm", align="center")
        current_y += h + 15

def fetch_pexels_image(query, api_key):
    try:
        url = f"https://api.pexels.com/v1/search?query={query}&per_page=1&orientation=portrait"
        response = requests.get(url, headers={"Authorization": api_key}, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("photos"):
                img_url = data["photos"][0]["src"]["large2x"]
                return Image.open(BytesIO(requests.get(img_url, timeout=15).content))
    except: return None
    return None

# 5. 실행 로직
if st.button("🚀 카드뉴스 5장 생성하기"):
    if not gemini_key or not user_topic:
        st.warning("API 키와 주제를 확인하세요.")
    else:
        with st.spinner("AI가 기획 및 디자인을 진행 중입니다..."):
            # 공유해주신 모델 리스트 기반 연결 시도
            models_to_try = ['gemini-2.0-flash', 'gemini-2.0-flash-lite', 'gemini-3.1-flash-lite', 'gemini-3.5-flash', 'gemini-1.5-flash']
            model, connected_model = None, ""
            
            for m_name in models_to_try:
                try:
                    test_m = genai.GenerativeModel(m_name)
                    test_m.generate_content("Hi", generation_config={"max_output_tokens": 5})
                    model, connected_model = test_m, m_name
                    break
                except: continue
            
            if not model:
                st.error("연결 가능한 모델을 찾지 못했습니다.")
            else:
                prompt = f"주제: '{user_topic}'\n인스타그램 카드뉴스 5장 기획. JSON 배열로 출력할 것. 키: slide_num, main_en, sub_ko, sub_ja, search_keyword."
                response = model.generate_content(prompt)
                
                json_text = response.text.replace("```json", "").replace("```", "").strip()
                slides_data = json.loads(json_text)
                
                width, height = 1080, 1350
                font_en = ImageFont.truetype(font_path, 90) if font_path else ImageFont.load_default()
                font_ko = ImageFont.truetype(font_path, 45) if font_path else ImageFont.load_default()
                font_ja = ImageFont.truetype(font_path, 35) if font_path else ImageFont.load_default()
                
                generated_images = []
                for idx, slide in enumerate(slides_data):
                    bg = fetch_pexels_image(slide.get("search_keyword", "abstract"), pexels_key) if pexels_key else None
                    if bg:
                        bg = bg.resize((width, height), Image.Resampling.LANCZOS)
                        bg = ImageEnhance.Brightness(bg).enhance(0.4)
                        color_main, color_sub, outline = "#FFFFFF", "#E5E7EB", "#000000"
                    else:
                        bg = Image.new("RGB", (width, height), color=random.choice(["#FFB3BA", "#FFDFBA", "#FFFFBA", "#BAFFC9", "#BAE1FF"]))
                        color_main, color_sub, outline = "#111827", "#374151", "#FFFFFF"
                    
                    draw = ImageDraw.Draw(bg)
                    draw.rectangle([60, 60, width-60, height-60], outline=color_main, width=4)
                    
                    draw_wrapped_text_with_outline(draw, (width//2, height//3), slide.get("main_en", ""), font_en, color_main, outline, width-240)
                    draw_wrapped_text_with_outline(draw, (width//2, height//2+100), slide.get("sub_ko", ""), font_ko, color_sub, outline, width-240)
                    draw_wrapped_text_with_outline(draw, (width//2, height//2+250), slide.get("sub_ja", ""), font_ja, color_sub, outline, width-300, is_japanese=True)
                    
                    fname = f"slide_{idx+1}.png"
                    bg.save(fname)
                    generated_images.append((fname, bg))
                
                st.success("완성되었습니다!")
                cols = st.columns(5)
                for i, (fname, img) in enumerate(generated_images):
                    with cols[i]:
                        st.image(img, use_container_width=True)
                        with open(fname, "rb") as f: st.download_button("💾 다운", f, fname)
