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

st.title("🎨 AI 인스타 카드뉴스 공장 (v3.0 다국어 & Pexels 에디션)")
st.write("주제를 입력하면 기획부터 디자인(영/한/일)까지 AI가 자동으로 완성합니다.")

# 2. API 키 설정 (Gemini & Pexels)
st.sidebar.header("🔑 API 키 설정")
env_gemini = os.environ.get("GEMINI_API_KEY", "")
env_pexels = os.environ.get("PEXELS_API_KEY", "")

# Gemini API Key
if env_gemini:
    st.sidebar.success("Gemini API 키 연동 완료 ✅")
    gemini_key = env_gemini
else:
    gemini_key = st.sidebar.text_input("Gemini API Key를 입력하세요", type="password")

# Pexels API Key
if env_pexels:
    st.sidebar.success("Pexels API 키 연동 완료 ✅")
    pexels_key = env_pexels
else:
    pexels_key = st.sidebar.text_input("Pexels API Key (선택/무료)", type="password")
    st.sidebar.info("💡 Pexels API 키를 넣으면 고화질 실사 이미지를 가져오며, 없으면 파스텔 톤 배경이 적용됩니다.")

if gemini_key:
    genai.configure(api_key=gemini_key)

# 3. 폰트 다운로드 (영/한/일 통합 지원 CJK 폰트)
@st.cache_resource
def load_assets():
    font_url = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Korean/NotoSansCJKkr-Bold.otf"
    font_path = "CustomFont.otf"
    if not os.path.exists(font_path):
        try:
            with open(font_path, "wb") as f:
                f.write(requests.get(font_url, timeout=15).content)
        except Exception:
            return None
    return font_path

font_path = load_assets()

user_topic = st.text_input("✍️ 제작하고 싶은 카드뉴스 주제를 입력하세요", placeholder="예: 테슬라 FSD의 혁신적인 기술력")

# 4. [개선] 단어(어절) 단위 자동 개행 알고리즘
def wrap_text_by_word(text, font, max_width, draw):
    words = text.split(" ")
    lines = []
    current_line = ""
    
    for word in words:
        test_line = f"{current_line} {word}".strip()
        bbox = draw.textbbox((0, 0), test_line, font=font)
        width = bbox[2] - bbox[0]
        
        if width <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
            
            # 혹시 단어 하나가 캔버스보다 길 경우를 대비한 안전장치
            if draw.textbbox((0, 0), current_line, font=font)[2] > max_width:
                lines.append(current_line)
                current_line = ""
                
    if current_line:
        lines.append(current_line)
    return lines

# 아웃라인 포함 텍스트 렌더링 함수
def draw_wrapped_text_with_outline(draw, position, text, font, text_color, outline_color, max_width, line_spacing=15, outline_width=4):
    lines = wrap_text_by_word(text, font, max_width, draw)
    
    if not lines: return
    
    line_heights = [draw.textbbox((0, 0), line, font=font)[3] - draw.textbbox((0, 0), line, font=font)[1] for line in lines]
    total_height = sum(line_heights) + line_spacing * (len(lines) - 1)
    current_y = position[1] - total_height // 2
    
    for line, h in zip(lines, line_heights):
        x = position[0]
        y = current_y + h // 2
        
        # 외곽선 그리기
        if outline_width > 0:
            for dx in range(-outline_width, outline_width + 1):
                for dy in range(-outline_width, outline_width + 1):
                    if dx != 0 or dy != 0:
                        draw.text((x + dx, y + dy), line, fill=outline_color, font=font, anchor="mm", align="center")
        
        # 본 텍스트 그리기
        draw.text((x, y), line, fill=text_color, font=font, anchor="mm", align="center")
        current_y += h + line_spacing

# 5. Pexels 이미지 검색 함수
def fetch_pexels_image(query, api_key):
    try:
        url = f"https://api.pexels.com/v1/search?query={query}&per_page=1&orientation=portrait"
        headers = {"Authorization": api_key}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("photos"):
                img_url = data["photos"][0]["src"]["large2x"]
                img_data = requests.get(img_url, timeout=15).content
                return Image.open(BytesIO(img_data))
    except Exception as e:
        print(f"Pexels fetch error: {e}")
    return None

# 파스텔 톤 팔레트
PASTEL_COLORS = ["#FFB3BA", "#FFDFBA", "#FFFFBA", "#BAFFC9", "#BAE1FF", "#E2F0CB", "#F4CBFF"]

# 6. 실행 버튼 동작
if st.button("🚀 카드뉴스 5장 생성하기"):
    if not gemini_key:
        st.warning("먼저 Gemini API Key를 세팅해 주세요!")
    elif not user_topic:
        st.warning("주제를 입력해 주세요!")
    else:
        with st.spinner("AI가 다국어 기획 및 디자인을 진행 중입니다. 잠시만 기다려주세요..."):
            
            try:
                # 모델 연결
                model = genai.GenerativeModel("gemini-1.5-flash") # 최신 빠르고 저렴한 모델 명시적 지정
                
                # [개선] 다국어(영/한/일) 및 Pexels 검색용 영문 키워드 프롬프트
                prompt = f"주제: '{user_topic}'\n"
                prompt += "인스타그램 카드뉴스 5장 세트의 기획을 작성해.\n"
                prompt += "각 슬라이드는 다음 키를 포함해야 해:\n"
                prompt += "- slide_num: (숫자)\n"
                prompt += "- main_en: 핵심 메시지 (영어, 2~5단어 내외)\n"
                prompt += "- sub_ko: 세부 내용 (한국어, 1~2문장)\n"
                prompt += "- sub_ja: 세부 내용 (일본어, 1~2문장)\n"
                prompt += "- search_keyword: 배경 이미지 검색을 위한 시각적이고 구체적인 '영어 단어 1개' (예: Technology, Future, Relax)\n"
                prompt += "반드시 JSON 형태(slides 배열)로만 출력할 것."
                
                # JSON 응답 요청
                response = model.generate_content(prompt)
                
                # 마크다운 블록(```json ... ```) 제거 로직 추가
                json_text = response.text.strip()
                if json_text.startswith("```"):
                    json_text = json_text.split("\n", 1)[1]
                    if json_text.endswith("```"):
                        json_text = json_text.rsplit("\n", 1)[0]
                        
                response_data = json.loads(json_text)
                
                if isinstance(response_data, dict) and "slides" in response_data:
                    slides_data = response_data["slides"]
                elif isinstance(response_data, list):
                    slides_data = response_data
                else:
                    raise ValueError("올바른 JSON 형식이 아닙니다.")
                
                width, height = 1080, 1350
                
                # 폰트 로드 (크기 차등화)
                if font_path and os.path.exists(font_path):
                    font_en = ImageFont.truetype(font_path, 90)  # 영어 메인 (가장 크게)
                    font_ko = ImageFont.truetype(font_path, 45)  # 한글 서브
                    font_ja = ImageFont.truetype(font_path, 35)  # 일어 서브 (조금 더 작게)
                    font_num = ImageFont.truetype(font_path, 30)
                else:
                    font_en = font_ko = font_ja = font_num = ImageFont.load_default()
                
                generated_images = []
                progress_bar = st.progress(0)
                
                for idx, slide in enumerate(slides_data):
                    keyword = slide.get("search_keyword", "abstract")
                    bg = None
                    is_image_bg = False
                    
                    # 1. Pexels API로 이미지 시도
                    if pexels_key:
                        bg = fetch_pexels_image(keyword, pexels_key)
                        if bg:
                            bg = bg.resize((width, height), Image.Resampling.LANCZOS)
                            is_image_bg = True
                    
                    # 2. 이미지 실패 또는 API 키 없을 때 파스텔 배경(Fallback) 적용
                    if not bg:
                        bg_color = random.choice(PASTEL_COLORS)
                        bg = Image.new("RGB", (width, height), color=bg_color)
                        is_image_bg = False

                    draw = ImageDraw.Draw(bg)
                    margin = 60
                    
                    # 테두리 및 컬러 테마 설정
                    if is_image_bg:
                        # 이미지 배경: 어둡게 누르고, 흰색 텍스트에 검정 외곽선
                        enhancer = ImageEnhance.Brightness(bg)
                        bg = enhancer.enhance(0.4) # 60% 어둡게
                        draw = ImageDraw.Draw(bg)
                        
                        text_main = "#FFFFFF" # 흰색
                        text_sub = "#E5E7EB"  # 밝은 회색
                        outline = "#000000"
                        draw.rectangle([margin, margin, width - margin, height - margin], outline="#FFFFFF", width=4)
                        draw.text((width - 100, 100), f"{idx+1} / 5", fill="#FFFFFF", font=font_num, anchor="rt")
                    else:
                        # 파스텔 배경: 밝게 유지하고, 어두운 텍스트에 흰색 외곽선
                        text_main = "#111827" # 진한 검회색
                        text_sub = "#374151"  # 중간 검회색
                        outline = "#FFFFFF"   # 파스텔톤 위에서 가독성 높이는 흰색 테두리
                        draw.rectangle([margin, margin, width - margin, height - margin], outline="#111827", width=4)
                        draw.text((width - 100, 100), f"{idx+1} / 5", fill="#111827", font=font_num, anchor="rt")

                    max_text_width = width - (margin * 4)
                    
                    # [개선] 다국어 텍스트 시각적 계층 배치 (위치 이원화)
                    # 1. 영문 (중앙 상단)
                    draw_wrapped_text_with_outline(draw, (width // 2, height // 3), slide.get("main_en", ""), font_en, text_main, outline, max_text_width, outline_width=3)
                    
                    # 2. 한글 (중앙 하단)
                    draw_wrapped_text_with_outline(draw, (width // 2, height // 2 + 100), slide.get("sub_ko", ""), font_ko, text_sub, outline, max_text_width, outline_width=2)
                    
                    # 3. 일어 (한글 바로 아래)
                    draw_wrapped_text_with_outline(draw, (width // 2, height // 2 + 250), slide.get("sub_ja", ""), font_ja, text_sub, outline, max_text_width, outline_width=2)
                    
                    filename = f"slide_{idx+1}.png"
                    bg.save(filename)
                    generated_images.append((filename, bg))
                    
                    progress_bar.progress((idx + 1) / 5)
                    time.sleep(0.1)
                
                st.balloons()
                st.success("🎉 다국어 카드뉴스가 완벽하게 완성되었습니다!")
                
                cols = st.columns(5)
                for i, (fname, img) in enumerate(generated_images):
                    with cols[i]:
                        st.image(img, caption=f"{i+1}번 슬라이드", use_container_width=True)
                        with open(fname, "rb") as file:
                            st.download_button(label=f"💾 다운", data=file, file_name=fname, mime="image/png", key=f"btn_{i}")
                            
            except Exception as ex:
                st.error(f"생성 중 에러가 발생했습니다: {str(ex)}")