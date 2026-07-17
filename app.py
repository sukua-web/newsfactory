import streamlit as st
import os
import requests
import json
import time
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import google.generativeai as genai

# 1. 페이지 설정 최상단 고정 (Streamlit 필수 규칙)
st.set_page_config(page_title="AI 인스타 카드뉴스 공장", page_icon="🎨", layout="centered")

st.title("🎨 AI 인스타 카드뉴스 공장 (v2.5 Server Edition)")
st.write("주제를 입력하면 기획부터 디자인까지 AI가 자동으로 완성합니다.")

# 2. API 키 설정 (보안 환경변수 최우선 선점, 없을 경우 화면 입력)
env_key = os.environ.get("GEMINI_API_KEY", "")
st.sidebar.header("🔑 API 키 설정")

if env_key:
    st.sidebar.success("서버 환경변수(Secrets) 연동 완료 ✅")
    gemini_key = env_key
else:
    gemini_key = st.sidebar.text_input("Gemini API Key를 입력하세요", type="password")
    st.sidebar.info("💡 배포 설정(Secrets)에 키를 등록하면 매번 입력하지 않아도 됩니다.")

if gemini_key:
    genai.configure(api_key=gemini_key)

# 3. 폰트 다운로드 (배포 환경 호환 캐싱)
@st.cache_resource
def load_assets():
    font_url = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Korean/NotoSansCJKkr-Bold.otf"
    font_path = "CustomFont.otf"
    if not os.path.exists(font_path):
        try:
            with open(font_path, "wb") as f:
                f.write(requests.get(font_url, timeout=15).content)
        except Exception:
            # 다운로드 실패 시 시스템 기본 폰트 사용을 위한 처리
            return None
    return font_path

font_path = load_assets()

user_topic = st.text_input("✍️ 제작하고 싶은 카드뉴스 주제를 입력하세요", placeholder="예: 무기력을 극복하는 현실적인 3가지 방법")

# 4. 텍스트 자동 개행 알고리즘
def wrap_text(text, font, max_width, draw):
    lines = []
    current_line = ""
    for char in text:
        test_line = current_line + char
        bbox = draw.textbbox((0, 0), test_line, font=font)
        width = bbox[2] - bbox[0]
        if width <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = char
    if current_line:
        lines.append(current_line)
    return lines

# 5. 아웃라인 포함 텍스트 렌더링
def draw_wrapped_text_with_outline(draw, position, text, font, text_color, outline_color, max_width, line_spacing=15, outline_width=4):
    lines = wrap_text(text, font, max_width, draw)
    line_heights = [draw.textbbox((0, 0), line, font=font)[3] - draw.textbbox((0, 0), line, font=font)[1] for line in lines]
    
    total_height = sum(line_heights) + line_spacing * (len(lines) - 1)
    current_y = position[1] - total_height // 2
    
    for line, h in zip(lines, line_heights):
        x = position[0]
        y = current_y + h // 2
        for dx in range(-outline_width, outline_width + 1):
            for dy in range(-outline_width, outline_width + 1):
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), line, fill=outline_color, font=font, anchor="mm", align="center")
        draw.text((x, y), line, fill=text_color, font=font, anchor="mm", align="center")
        current_y += h + line_spacing

# 6. 실행 버튼 동작
if st.button("🚀 카드뉴스 5장 생성하기"):
    if not gemini_key:
        st.warning("먼저 Gemini API Key를 세팅해 주세요!")
    elif not user_topic:
        st.warning("주제를 입력해 주세요!")
    else:
        with st.spinner("AI가 기획 및 디자인을 진행 중입니다. 잠시만 기다려주세요..."):
            
            # 모델 목록 자동 스캔 로직
            model = None
            error_msg = ""
            connected_model_name = ""
            
            try:
                available_models = []
                for m in genai.list_models():
                    if 'generateContent' in m.supported_generation_methods and 'gemini' in m.name.lower():
                        clean_name = m.name.replace('models/', '')
                        available_models.append(clean_name)
                
                if not available_models:
                    error_msg = "이 API 키로 조회 가능한 Gemini 모델이 없습니다."
                else:
                    available_models.sort(key=lambda x: (0 if 'flash' in x else 1, x))
                    for model_name in available_models:
                        try:
                            test_model = genai.GenerativeModel(model_name)
                            test_model.generate_content("Hi", generation_config={"max_output_tokens": 5})
                            model = test_model
                            connected_model_name = model_name
                            break
                        except Exception as e:
                            error_msg += f"[{model_name} 실패: {str(e)}]\n"
                            continue
            except Exception as e:
                error_msg = f"모델 목록 조회 자체 실패: {str(e)}"
            
            if not model:
                st.error(f"⚠️ 연결 가능한 AI 모델을 찾지 못했습니다.\n\n**상세 에러 원인:**\n{error_msg}")
            else:
                st.info(f"✅ 구글 AI 연결 성공! (사용 중인 모델: **{connected_model_name}**)")
                
                prompt = f"주제: '{user_topic}'\n"
                prompt += "인스타그램 카드뉴스 5장 세트의 기획을 작성해.\n"
                prompt += "각 슬라이드는 다음 키를 포함해야 해: slide_num(숫자), title(제목), subtitle(본문), description(하단 안내), keyword(배경용 영문 1단어)\n"
                prompt += "반드시 JSON 배열 형태로만 출력할 것."
                
                try:
                    # JSON 출력 강제 규칙
                    response = model.generate_content(
                        prompt,
                        generation_config={"response_mime_type": "application/json"}
                    )
                    
                    response_data = json.loads(response.text)
                    
                    if isinstance(response_data, dict) and "slides" in response_data:
                        slides_data = response_data["slides"]
                    elif isinstance(response_data, list):
                        slides_data = response_data
                    else:
                        raise ValueError("AI가 올바른 JSON 데이터를 반환하지 않았습니다.")
                    
                    # 이미지 캔버스 크기 및 폰트 설정
                    width, height = 1080, 1350
                    if font_path and os.path.exists(font_path):
                        title_font = ImageFont.truetype(font_path, 72)
                        subtitle_font = ImageFont.truetype(font_path, 42)
                        desc_font = ImageFont.truetype(font_path, 32)
                    else:
                        title_font = ImageFont.load_default()
                        subtitle_font = ImageFont.load_default()
                        desc_font = ImageFont.load_default()
                    
                    generated_images = []
                    progress_bar = st.progress(0)
                    
                    for idx, slide in enumerate(slides_data):
                        keyword = slide.get("keyword", "nature")
                        # [개선] 크롤링 차단이 없는 안정적인 Unsplash Source로 교체
                        img_url = f"https://images.unsplash.com/photo-1506744038136-46273834b3fb?auto=format&fit=crop&w={width}&h={height}&q=80"
                        if keyword and keyword != "abstract":
                            img_url = f"https://source.unsplash.com/featured/{width}x{height}/?{keyword}"
                        
                        try:
                            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                            img_data = requests.get(img_url, headers=headers, timeout=15).content
                            filename_bg = f"temp_bg_{idx}.jpg"
                            with open(filename_bg, "wb") as handler:
                                handler.write(img_data)
                            bg = Image.open(filename_bg)
                        except Exception:
                            # 이미지 다운로드 실패 시 고급스러운 다크 네이비 단색 배경 적용
                            bg = Image.new("RGB", (width, height), color="#0F172A")

                        # 글자가 잘 보이도록 배경을 85% 어둡게 조정
                        enhancer = ImageEnhance.Brightness(bg)
                        bg_dark = enhancer.enhance(0.15)
                        draw = ImageDraw.Draw(bg_dark)
                        
                        # 테두리 및 슬라이드 번호 그리기
                        margin = 60
                        draw.rectangle([margin, margin, width - margin, height - margin], outline="#FFFFFF", width=3)
                        draw.text((width - 120, 120), f"{idx+1} / 5", fill="#9CA3AF", font=desc_font, anchor="rt")
                        
                        max_text_width = width - (margin * 4)
                        title_color = "#F59E0B" if (idx+1) <= 1 or (idx+1) == 5 else "#FFFFFF"
                        
                        # 카드뉴스 텍스트 배치
                        draw_wrapped_text_with_outline(draw, (width // 2, height // 3 + 20), str(slide.get("title", "")), title_font, title_color, "#000000", max_text_width)
                        draw_wrapped_text_with_outline(draw, (width // 2, height // 2 + 150), str(slide.get("subtitle", "")), subtitle_font, "#FFFFFF", "#000000", max_text_width)
                        draw_wrapped_text_with_outline(draw, (width // 2, height - 180), str(slide.get("description", "")), desc_font, "#E5E7EB", "#000000", max_text_width)
                        
                        filename = f"slide_{idx+1}.png"
                        bg_dark.save(filename)
                        generated_images.append((filename, bg_dark))
                        
                        progress_bar.progress((idx + 1) / 5)
                        time.sleep(0.1)
                    
                    st.balloons()
                    st.success("🎉 카드뉴스가 완벽하게 완성되었습니다!")
                    
                    # 완성 이미지 및 다운로드 버튼 레이아웃 출력
                    cols = st.columns(5)
                    for i, (fname, img) in enumerate(generated_images):
                        with cols[i]:
                            st.image(img, caption=f"{i+1}번 슬라이드", use_container_width=True)
                            with open(fname, "rb") as file:
                                st.download_button(label=f"💾 다운", data=file, file_name=fname, mime="image/png", key=f"btn_{i}")
                                
                except Exception as ex:
                    st.error(f"생성 중 에러가 발생했습니다: {str(ex)}")