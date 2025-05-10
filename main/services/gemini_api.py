# C:/Users/wjddb/PycharmProjects/APAC_BarrierFreeJourney/main/views/gemini_api.py
import google.generativeai as genai
from django.conf import settings
import json  # JSON 파싱 및 오류 처리를 위해 추가
import logging
from .places_api import find_places_by_text_search
from datetime import timedelta

LIMIT=5
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
    if not settings.GOOGLE_PLACES_API_KEY:
        logger.error("Google Places API Key is not configured in settings.")
        raise ValueError("Google Places API Key is not configured.")

    genai.configure(api_key=settings.GEMINI_API_KEY)  # 함수 호출 시점에 configure
    model_name = 'gemini-1.5-flash-latest'
    try:
        model = genai.GenerativeModel(model_name)
    except Exception as e:
        logger.error(f"Failed to initialize Gemini model ({model_name}): {e}")
        raise  RuntimeError(f"Failed to initialize Gemini model: {e}") # 모델 초기화 실패 시 예외 발생

    travel_dates = []
    current_date = travel_request.start_date
    while current_date <= travel_request.end_date:
        travel_dates.append(current_date.strftime('%Y-%m-%d'))
        current_date += timedelta(days=1)

    if not travel_dates:  # 여행 기간이 없는 경우 (예: start_date > end_date)
        logger.error(f"Invalid travel period for TravelRequest ID {travel_request.id}: start_date > end_date.")
        raise ValueError("Invalid travel period: Start date must be before or same as end date.")

    # 프롬프트 개선: JSON 구조 및 필드, 제약사항 명확화
    # place_id는 Gemini가 생성하는 임의의 정수 ID (place_id_from_ai)로 명시
    # ScheduleItem.place_id (IntegerField)와 호환되도록.
    primary_city = travel_request.cities[0] if travel_request.cities else "the specified city"

    # places_api 로부터 interest × mood 조합에 맞는 실제 장소 수집
    real_places = []
    logger.info(f"Starting to fetch real places for TR ID {travel_request.id}...")
    for city in travel_request.cities:
        for interest in travel_request.interests:
            for mood in travel_request.mood:
                query = f"{mood} {interest}"
                places_found = find_places_by_text_search(
                    query_text=query,
                    city_name=city,
                    type_filter=None,  # 필요시 "restaurant", "cafe", "museum" 등 구체적 타입 지정
                    limit=LIMIT  # 각 검색어당 가져올 장소 수
                )
                real_places.extend(places_found)
    logger.info(f"Fetched a total of {len(real_places)} places (before deduplication) for TR ID {travel_request.id}.")
    # 중복 제거 (place_id 기준)
    seen_ids = set()
    unique_places = []
    for place in real_places:
        pid = place.get("place_id")
        if pid and pid not in seen_ids:
            seen_ids.add(pid)
            unique_places.append(place)
    logger.info(f"Number of unique places found for TR ID {travel_request.id}: {len(unique_places)}")

    if not unique_places:
        logger.warning(
            f"No unique real places found from Places API for TR ID {travel_request.id}. Cannot generate schedule with Gemini.")

    places_json = json.dumps(unique_places, ensure_ascii=False)

    prompt = f"""
    You are a travel planning assistant.
    Your task is to create a travel itinerary based on the User's Travel Request Details using ONLY the places provided in the "List of Real, Verified Places" below.
    If the "List of Real, Verified Places" is empty or contains too few places to build a meaningful itinerary, you MUST respond with a JSON object containing an empty "schedule_items" list and an "error_message" field explaining that not enough places were found.

    List of Real, Verified Places (fetched from Google Maps API):
    {places_json}

    **Instructions for building the itinerary:**
    - Use ONLY the places from the list above. Do NOT invent any other venues.
    - Each item in the "schedule_items" list MUST correspond to one of the places in the "List of Real, Verified Places".
    - The "place_id" in your schedule item MUST be the "place_id" from the list.
    - The "place_name", "lat", "lng", and "address" in your schedule item MUST come directly from the corresponding place in the list.
    - Assign a "date" (from the travel period), "start_time", "end_time", and "transport_type" for each selected place.

    User's Travel Request Details:
    - Country: {travel_request.country}
    - Cities: {', '.join(travel_request.cities)}
    - Travel Period: From {travel_request.start_date.strftime('%Y-%m-%d')} to {travel_request.end_date.strftime('%Y-%m-%d')} (Available dates for schedule: {', '.join(travel_dates)})
    - Interests: {', '.join(travel_request.interests) if travel_request.interests else 'Not specified'}
    - Desired Mood: {', '.join(travel_request.mood) if travel_request.mood else 'Not specified'}
    - Preferred Transportation: {', '.join(travel_request.transportation) if travel_request.transportation else 'Not specified'}
    - Max Travel Distance per day (if applicable): {travel_request.max_distance} km

    **Output Format:**
    The entire response MUST be a single valid JSON object.
    The JSON object should have a key "schedule_items" which is a list of schedule item objects.
    If you cannot create a schedule (e.g., no places provided or too few), "schedule_items" should be an empty list, and you MUST include an "error_message" field.

    Example of a single schedule item object (using data from the provided list):
    {{
        "place_name": "Name From List",
        "place_id": "PlaceID From List",
        "date": "{travel_dates[0] if travel_dates else 'YYYY-MM-DD'}",
        "start_time": "10:00",
        "end_time": "12:00",
        "lat": 12.3456, // Latitude From List
        "lng": 78.9012, // Longitude From List
        "transport_type": "walk",
        "address": "Full Address From List"
    }}

    Example of response if no places are found or schedule cannot be made:
    {{
        "schedule_items": [],
        "error_message": "Not enough relevant places were found based on your request to create a schedule."
    }}

    Generate a plausible and enjoyable itinerary. Ensure all dates are within the travel period.
    Do not include any other text, explanations, or markdown formatting outside the main JSON object.
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



