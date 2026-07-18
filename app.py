import streamlit as st
import os
import requests
import json
import random
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import google.generativeai as genai
from serpapi import GoogleSearch

# 1. 페이지 설정
st.set_page_config(page_title="AI 인스타 카드뉴스 공장", page_icon="🎨", layout="centered")

st.title("🎨 AI 인스타 카드뉴스 공장 (v3.3 SerpApi)")

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

# 4. 이미지 검색 함수 (SerpApi 사용)
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
        
        if "images_results" in results and len(results["images_results"]) > 0:
            img_url = results["images_results"][0]["original"]
            img_response = requests.get(img_url, timeout=10)
            return Image.open(BytesIO(img_response.content))
    except Exception as e:
        st.error(f"이미지 검색 실패: {e}")
    return None

# 5. 그리기 헬퍼 함수들 (기존과 동일)
def wrap_text_by_word(text, font, max_width, draw, is_japanese=False):
    if is_japanese:
        chars_per_line = 18
        lines = [text[i:i + chars_per_line] for i in range(0, len(text), chars_per_line)]
        return lines
    else:
        words = str(text).split(" ")
        lines, current_line = [], ""
        for word in words:
            test_line = f"{current_line} {word}".strip()
            if draw.textbbox((0, 0), test_line, font=font)[2] <= max_width:
                current_line = test_line
            else:
                if current_line: lines.append(current_line)
                current_line = word
        if current_line: lines.append(current_line)
        return lines

def draw_wrapped_text_with_outline(draw, position, text, font, text_color, outline_color, max_width, outline_width=2, is_japanese=False):
    lines = wrap_text_by_word(text, font, max_width, draw, is_japanese=is_japanese)
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

def draw_japanese_text_forced(draw, position, text, font, text_color, outline_color, outline_width=2):
    lines = [text[i:i+16] for i in range(0, len(text), 16)]
    line_height = font.getbbox("あ")[3] - font.getbbox("あ")[1]
    current_y = position[1]
    for line in lines:
        x, y = position[0], current_y
        for dx in range(-outline_width, outline_width+1):
            for dy in range(-outline_width, outline_width+1):
                draw.text((x+dx, y+dy), line, fill=outline_color, font=font, anchor="mm", align="center")
        draw.text((x, y), line, fill=text_color, font=font, anchor="mm", align="center")
        current_y += (line_height + 40)

# 6. 실행 로직
if st.button("🚀 카드뉴스 5장 생성하기"):
    if not gemini_key or not user_topic:
        st.warning("API 키와 주제를 확인하세요.")
    else:
        with st.spinner("AI가 작업 중입니다..."):
            model = genai.GenerativeModel('gemini-1.5-flash')
            prompt = f"주제: '{user_topic}'\n인스타그램 카드뉴스 5장 기획. JSON 배열로 출력. 키: slide_num, main_en, sub_ko, sub_ja, search_keyword."
            response = model.generate_content(prompt)
            
            json_text = response.text.replace("```json", "").replace("```", "").strip()
            slides_data = json.loads(json_text)
            
            width, height = 1080, 1350
            font_en = ImageFont.truetype(font_path, 90)
            font_ko = ImageFont.truetype(font_path, 45)
            font_ja = ImageFont.truetype(font_path, 35)
            
            generated_images = []
            for idx, slide in enumerate(slides_data):
                # SerpApi 이미지 검색 호출
                bg = fetch_serpapi_image(slide.get("search_keyword", user_topic), serpapi_key) if serpapi_key else None
                
                if bg:
                    bg = bg.resize((width, height), Image.Resampling.LANCZOS)
                    bg = ImageEnhance.Brightness(bg).enhance(0.4)
                    c_main, c_sub, out = "#FFFFFF", "#E5E7EB", "#000000"
                else:
                    bg = Image.new("RGB", (width, height), color=random.choice(["#FFB3BA", "#FFDFBA", "#FFFFBA", "#BAFFC9", "#BAE1FF"]))
                    c_main, c_sub, out = "#111827", "#374151", "#FFFFFF"
                
                draw = ImageDraw.Draw(bg)
                draw.rectangle([60, 60, width-60, height-60], outline=c_main, width=4)
                draw_wrapped_text_with_outline(draw, (width//2, height//3), slide.get("main_en", ""), font_en, c_main, out, width-240)
                draw_wrapped_text_with_outline(draw, (width//2, height//2+100), slide.get("sub_ko", ""), font_ko, c_sub, out, width-240)
                draw_japanese_text_forced(draw, (width//2, height//2+300), slide.get("sub_ja", ""), font_ja, c_sub, out)
                
                fname = f"slide_{idx+1}.png"
                bg.save(fname)
                generated_images.append((fname, bg))
            
            st.success("완성!")
            cols = st.columns(5)
            for i, (fname, img) in enumerate(generated_images):
                with cols[i]:
                    st.image(img, use_container_width=True)
                    with open(fname, "rb") as f: st.download_button("💾 다운", f, fname)