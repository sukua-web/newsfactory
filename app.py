import os
import json
import time
import smtplib
import requests
import xml.etree.ElementTree as ET
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import google.generativeai as genai

# 1. 환경 변수에서 비밀키 로드 (보안)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")      # 보내는 이메일 (내 Gmail)
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")  # Gmail 앱 비밀번호
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER")  # 받는 이메일 (내 이메일)

genai.configure(api_key=GEMINI_API_KEY)

# 2. 오늘의 뉴스 자동 수집 (구글 뉴스 RSS 활용 - 가장 안정적)
def get_today_news_topic():
    try:
        url = "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko"
        response = requests.get(url, timeout=10)
        root = ET.fromstring(response.content)
        # 가장 상단의 최신 주요 뉴스 헤드라인 1개 가져오기
        top_news_title = root.find('.//item/title').text
        # 언론사 이름 제거 (예: "뉴스제목 - 연합뉴스" -> "뉴스제목")
        if " - " in top_news_title:
            top_news_title = top_news_title.split(" - ")[0]
        return top_news_title
    except Exception as e:
        print(f"뉴스 수집 실패: {e}")
        return "오늘의 주요 시사 상식 및 트렌드 요약" # 실패 시 대체 주제

# 3. 이미지 위에 글자 쓰기 위한 개행 알고리즘
def wrap_text(text, font, max_width, draw):
    lines, current_line = [], ""
    for char in text:
        test_line = current_line + char
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            current_line = test_line
        else:
            if current_line: lines.append(current_line)
            current_line = char
    if current_line: lines.append(current_line)
    return lines

def draw_text_outline(draw, position, text, font, text_color, outline_color, max_width):
    lines = wrap_text(text, font, max_width, draw)
    line_heights = [draw.textbbox((0, 0), line, font=font)[3] - draw.textbbox((0, 0), line, font=font)[1] for line in lines]
    current_y = position[1] - (sum(line_heights) + 15 * (len(lines) - 1)) // 2
    for line, h in zip(lines, line_heights):
        x = position[0]
        y = current_y + h // 2
        for dx in [-3, 0, 3]:
            for dy in [-3, 0, 3]:
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), line, fill=outline_color, font=font, anchor="mm", align="center")
        draw.text((x, y), line, fill=text_color, font=font, anchor="mm", align="center")
        current_y += h + 15

# 4. 카드뉴스 메인 제작 로직
def create_card_news(user_topic):
    # 사용 가능한 Gemini 모델 스캔
    model_name = 'gemini-1.5-flash'
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods and 'flash' in m.name.lower():
                model_name = m.name.replace('models/', '')
                break
    except: pass
    
    model = genai.GenerativeModel(model_name)
    prompt = f"주제: '{user_topic}'\n인스타그램 카드뉴스 5장 세트 기획을 작성해.\nslide_num, title, subtitle, description, keyword(영문1단어) 키를 가진 JSON 배열만 출력해."
    
    response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
    slides_data = json.loads(response.text)
    if isinstance(slides_data, dict) and "slides" in slides_data:
        slides_data = slides_data["slides"]

    # 폰트 다운로드
    font_path = "CustomFont.otf"
    if not os.path.exists(font_path):
        font_url = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Korean/NotoSansCJKkr-Bold.otf"
        with open(font_path, "wb") as f: f.write(requests.get(font_url).content)

    width, height = 1080, 1350
    title_font = ImageFont.truetype(font_path, 72)
    subtitle_font = ImageFont.truetype(font_path, 42)
    desc_font = ImageFont.truetype(font_path, 32)
    
    image_paths = []
    
    for idx, slide in enumerate(slides_data):
        keyword = slide.get("keyword", "news")
        img_url = f"https://source.unsplash.com/featured/{width}x{height}/?{keyword}"
        try:
            img_data = requests.get(img_url, timeout=10).content
            bg = Image.open(BytesIO(img_data))
        except:
            bg = Image.new("RGB", (width, height), color="#0F172A")
            
        bg_dark = ImageEnhance.Brightness(bg).enhance(0.15)
        draw = ImageDraw.Draw(bg_dark)
        
        draw.rectangle([60, 60, width - 60, height - 60], outline="#FFFFFF", width=3)
        draw.text((width - 120, 120), f"{idx+1} / 5", fill="#9CA3AF", font=desc_font, anchor="rt")
        
        title_color = "#F59E0B" if idx == 0 or idx == 4 else "#FFFFFF"
        draw_text_outline(draw, (width // 2, height // 3 + 20), str(slide.get("title", "")), title_font, title_color, "#000000", width - 240)
        draw_text_outline(draw, (width // 2, height // 2 + 150), str(slide.get("subtitle", "")), subtitle_font, "#FFFFFF", "#000000", width - 240)
        draw_text_outline(draw, (width // 2, height - 180), str(slide.get("description", "")), desc_font, "#E5E7EB", "#000000", width - 240)
        
        filename = f"slide_{idx+1}.png"
        bg_dark.save(filename)
        image_paths.append(filename)
    
    return image_paths

# 5. 생성된 이미지를 이메일로 발송
def send_email(topic, image_paths):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg['Subject'] = f"📢 [자동 발송] 오늘의 AI 뉴스 카드뉴스: {topic}"
    
    body = f"안녕하세요.\n\nAI 공장이 오늘의 뉴스 [{topic}]를 기반으로 제작한 카드뉴스 5장을 첨부합니다.\n인스타그램에 바로 업로드해보세요!"
    msg.attach(MIMEText(body, 'plain'))
    
    for path in image_paths:
        with open(path, 'rb') as f:
            img_data = f.read()
        image = MIMEImage(img_data, name=os.path.basename(path))
        msg.attach(image)
        
    # SMTP 서버 연결 (Gmail 기준)
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(EMAIL_SENDER, EMAIL_PASSWORD)
    server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
    server.quit()
    print("📧 이메일 발송 성공!")

# 메인 실행
if __name__ == "__main__":
    today_topic = get_today_news_topic()
    print(f"오늘 선택된 뉴스 주제: {today_topic}")
    images = create_card_news(today_topic)
    send_email(today_topic, images)
