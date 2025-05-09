# C:/Users/wjddb/PycharmProjects/APAC_BarrierFreeJourney/main/views/gemini_api.py
import google.generativeai as genai
from django.conf import settings
import json  # JSON 파싱 및 오류 처리를 위해 추가
import logging

logger = logging.getLogger(__name__)


# API 키 설정은 모듈 로드 시 한 번만 수행하는 것이 좋습니다.
# settings.py에서 이미 키 로드 및 검증을 하고 있으므로, 여기서는 바로 사용합니다.
# genai.configure(api_key=settings.GEMINI_API_KEY) # 이 라인은 View 등 호출하는 쪽에서 한 번만 하거나, 앱 시작 시점에 하는 것이 더 일반적입니다.
# 또는, 각 함수 호출 시점에 API 키가 설정되었는지 확인하고 설정할 수 있습니다.
# 여기서는 settings.GEMINI_API_KEY가 유효하다고 가정합니다.

def generate_travel_schedule_from_gemini(travel_request):  # 함수명 변경 (Gemini 명시)
    """
    TravelRequest 객체를 받아, Gemini 모델을 통해 JSON 형식의 여행 일정 텍스트를 반환합니다.
    반환되는 JSON은 'schedule_items' 키를 가지며, 값은 일정 항목 객체들의 리스트입니다.
    각 항목은 place_name, place_id_from_ai, date, start_time, end_time, lat, lng,
    transport_type, address 필드를 포함해야 합니다.
    """
    if not settings.GEMINI_API_KEY:
        logger.error("Gemini API Key is not configured in settings.")
        raise ValueError("Gemini API Key is not configured.")

    genai.configure(api_key=settings.GEMINI_API_KEY)  # 함수 호출 시점에 configure
    model_name = 'gemini-1.5-flash-latest'
    try:
        model = genai.GenerativeModel(model_name)
    except Exception as e:
        logger.error(f"Failed to initialize Gemini model ({model_name}): {e}")
        raise  # 모델 초기화 실패 시 예외를 다시 발생

    # 프롬프트 개선: JSON 구조 및 필드, 제약사항 명확화
    # place_id는 Gemini가 생성하는 임의의 정수 ID (place_id_from_ai)로 명시
    # ScheduleItem.place_id (IntegerField)와 호환되도록.
    prompt = f"""
    You are a travel planning assistant. Your task is to generate a travel itinerary based on the user's request.
    The response MUST be a single, valid JSON object.
    This JSON object MUST contain a key named "schedule_items".
    The value of "schedule_items" MUST be a list of schedule item objects.
    Each schedule item object in the list MUST have the following fields:
    - "place_name": string (Name of the place or activity)
    - "place_id_from_ai": integer (A unique integer ID you generate for this place, e.g., 1, 2, 3... This is NOT a Google Place ID.)
    - "date": string (Date in YYYY-MM-DD format. Must be within the travel period: {travel_request.start_date.strftime('%Y-%m-%d')} to {travel_request.end_date.strftime('%Y-%m-%d')})
    - "start_time": string (Start time in HH:MM format, e.g., "09:00")
    - "end_time": string (End time in HH:MM format, e.g., "17:30")
    - "lat": float (Latitude of the place)
    - "lng": float (Longitude of the place)
    - "transport_type": string (Recommended mode of transport to this place from the previous one. Examples: "walk", "bus", "subway", "taxi", "car_rental")
    - "address": string (Full address of the place, if available. If not, provide city and country at least.)

    User's Travel Request Details:
    - Country: {travel_request.country}
    - Cities: {', '.join(travel_request.cities)}
    - Travel Period: From {travel_request.start_date.strftime('%Y-%m-%d')} to {travel_request.end_date.strftime('%Y-%m-%d')}
    - Interests: {', '.join(travel_request.interests) if travel_request.interests else 'Not specified'}
    - Desired Mood: {', '.join(travel_request.mood) if travel_request.mood else 'Not specified'}
    - Preferred Transportation: {', '.join(travel_request.transportation) if travel_request.transportation else 'Not specified'}
    - Max Travel Distance per day (if applicable, for walking/cycling): {travel_request.max_distance} km

    Example of a single schedule item object:
    {{
        "place_name": "Eiffel Tower",
        "place_id_from_ai": 101,
        "date": "{travel_request.start_date.strftime('%Y-%m-%d')}",
        "start_time": "10:00",
        "end_time": "12:00",
        "lat": 48.8584,
        "lng": 2.2945,
        "transport_type": "metro",
        "address": "Champ de Mars, 5 Av. Anatole France, 75007 Paris, France"
    }}

    Generate a plausible and enjoyable itinerary. Ensure all dates are within the travel period.
    The entire response must be ONLY the JSON object, starting with {{ and ending with }}.
    Do not include any other text, explanations, or markdown formatting like json.
    """

    # Gemini API 호출 시 JSON 모드 사용
    generation_config = genai.types.GenerationConfig(
        response_mime_type="application/json"
        # temperature=0.7 # 필요에 따라 창의성 조절
    )
    response = model.generate_content(prompt, generation_config=generation_config)
    text = response.text or response.candidates[0].content.parts[0].text
    logger.info(f"Gemini response: {text[:200]}")
    return text



