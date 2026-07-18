import streamlit as st
import os
import requests
import json
import time
import random
import re
import textwrap
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import google.generativeai as genai

# 페이지 설정
st.set_page_config(page_title="AI 카드뉴스 공장", layout="centered")
st.title("🎨 AI 인스타 카드뉴스 공장 (Final Stable v4.2)")

# 1. 입력창은 항상 상단 (UI 구조 수정)
st.sidebar.header("🔑 API 설정")
gemini_key = st.sidebar.text_input("Gemini API Key", type="password", value=os.environ.get("GEMINI_API_KEY", ""))
serpapi_key = st.sidebar.text_input("SerpApi Key", type="password", value=os.environ.get("SERPAPI_KEY", ""))
user_topic = st.text_input("✍️ 주제를 입력하세요")

# 2. 폰트 로드 (필수 사항 체크)
@st.cache_resource
def load_fonts():
    try:
        return {
            "en": ImageFont.truetype("fonts/NotoSans-Bold.ttf", 60),
            "ko": ImageFont.truetype("fonts/NotoSansKR-Bold.otf", 45),
            "ja": ImageFont.truetype("fonts/NotoSansJP-Bold.otf", 35),
        }
    except Exception as e:
        st.error(f"폰트를 찾을 수 없습니다 (fonts/ 폴더 확인): {e}")
        st.stop()

# 텍스트 줄바꿈 및 그리기
def draw_wrapped_text(draw, y_start, text, font, fill, width_limit, align="center"):
    lines = textwrap.wrap(text, width=25) # 폰트에 따라 조정 필요
    y = y_start
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        draw.text(((1080 - w) / 2, y), line, font=font, fill=fill, stroke_width=2, stroke_fill="black")
        y += 60

# 이미지 검색 (함수형 예외처리)
def fetch_serpapi_image(query, api_key):
    try:
        url = "https://serpapi.com/search"
        params = {"engine": "google_images", "q": query, "api_key": api_key, "ijn": "0"}
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        for img in resp.json().get("images_results", []):
            try:
                img_resp = requests.get(img["original"], timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
                ctype = img_resp.headers.get("Content-Type", "")
                if ctype.startswith("image/") and "svg" not in ctype:
                    return Image.open(BytesIO(img_resp.content)).convert("RGB")
            except: continue
    except: return None
    return None

# 메인 실행 로직
if st.button("🚀 카드뉴스 생성"):
    if not all([gemini_key, serpapi_key, user_topic]):
        st.warning("API 키와 주제를 모두 확인하세요.")
    else:
        genai.configure(api_key=gemini_key)
        fonts = load_fonts()
        
        # 모델 검증
        model = None
        for m_name in ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash", "gemini-1.5-flash"]:
            try:
                m = genai.GenerativeModel(m_name)
                m.generate_content("hi", generation_config={"max_output_tokens": 3})
                model = m
                break
            except: continue

        if not model:
            st.error("연결 가능한 모델이 없습니다.")
            st.stop()

        # 데이터 생성 및 파싱
        prompt = f"주제: '{user_topic}'. 인스타그램 카드뉴스 5장을 기획해줘. Return ONLY valid JSON. No markdown. 키: slide_num, main_en, sub_ko, sub_ja, search_keyword."
        response = model.generate_content(prompt)
        raw_text = getattr(response, "text", "")
        if not raw_text: st.error("Gemini 응답 없음"); st.stop()
        
        match = re.search(r'\[[\s\S]*?\]', raw_text)
        if not match: st.error("JSON 파싱 실패"); st.stop()
        
        try:
            slides_data = json.loads(match.group())
            if not isinstance(slides_data, list) or len(slides_data) != 5:
                raise ValueError("슬라이드 개수 오류")
        except Exception as e:
            st.error(f"데이터 형식 오류: {e}"); st.stop()

        cols = st.columns(5)
        for idx, slide in enumerate(slides_data):
            bg = None
            for _ in range(3):
                bg = fetch_serpapi_image(slide.get("search_keyword") or user_topic, serpapi_key)
                if bg: break
                time.sleep(0.5)
            
            if not bg: bg = Image.new("RGB", (1080, 1350), color="#333333")
            
            # 디자인 적용
            bg = bg.resize((1080, 1350), Image.Resampling.LANCZOS)
            bg = ImageEnhance.Brightness(bg).enhance(0.4) # 밝기 낮춤
            draw = ImageDraw.Draw(bg)
            
            # 중앙 정렬 텍스트 그리기
            draw_wrapped_text(draw, 400, slide.get("main_en", ""), fonts["en"], "white", 800)
            draw_wrapped_text(draw, 600, slide.get("sub_ko", ""), fonts["ko"], "white", 800)
            draw_wrapped_text(draw, 800, slide.get("sub_ja", ""), fonts["ja"], "white", 800)
            
            buf = BytesIO()
            bg.save(buf, format="PNG")
            buf.seek(0)
            
            with cols[idx]:
                st.image(buf, use_container_width=True)
                buf.seek(0)
                st.download_button(f"받기 {idx+1}", buf, f"slide_{idx+1}.png", "image/png")