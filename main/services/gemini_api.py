import google.generativeai as genai
from django.conf import settings
import json
import logging
from .places_api import find_places_by_text_search, get_place_details_with_wheelchair_info
from datetime import timedelta

logger = logging.getLogger(__name__)

# 각 관심사에 대한 Google Places API type 매핑
INTEREST_TO_PLACE_TYPE_MAP = {
    "맛집 탐방": ["restaurant", "meal_delivery", "meal_takeaway", "bakery"],
    "전시": ["museum", "art_gallery"],
    "문화유산": ["tourist_attraction", "museum"],
    "예쁜 카페": ["cafe", "bakery"],
    "랜드마크": ["tourist_attraction", "point_of_interest"],
    "자연": ["park", "campground", "zoo", "aquarium"],
    "쇼핑": ["shopping_mall", "department_store", "store"],
    "건축": ["point_of_interest"],
    "경관": ["point_of_interest"],
    "스포츠 관람": ["stadium", "gym"],
    "공연/관람": ["movie_theater", "stadium"],
    "액티비티": ["amusement_park", "tourist_attraction"],
    "종교": ["church", "mosque", "hindu_temple", "synagogue", "place_of_worship"],
    "시장": ["store", "point_of_interest"],
    "번화가": ["night_club", "bar", "restaurant", "store"],
}
DEFAULT_PLACE_API_LIMIT_PER_QUERY = 3  # 각 검색어당 가져올 장소 수 (테스트를 위해 줄임)
GEMINI_SUGGESTED_QUERY_COUNT = 3  # Gemini에게 요청할 검색어 제안 개수


# --- 새로운 함수: Gemini를 사용하여 검색어 제안 ---
def suggest_search_queries_by_gemini(interest, mood, city, travel_request):
    """
    Gemini를 사용하여 특정 관심사, 분위기, 도시에 맞는 Places API 검색어를 제안받습니다.
    """
    if not settings.GEMINI_API_KEY:
        logger.error("Gemini API Key for query suggestion is not configured.")
        return []  # API 키 없으면 빈 리스트 반환

    try:
        # 이 함수 내에서만 사용할 Gemini 모델 인스턴스 생성
        # genai.configure는 generate_travel_schedule_from_gemini 등 다른 곳에서 이미 호출될 수 있으므로,
        # 여기서는 모델 직접 생성 시도
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
    except Exception as e:
        logger.error(f"Failed to initialize Gemini model for query suggestion: {e}")
        return []

    prompt = f"""
    You are a creative travel assistant.
    A user is planning a trip to {city} and has the following preferences:
    - Interest: {interest}
    - Desired Mood: {mood}
    - Other interests: {', '.join(list(set(travel_request.interests) - {interest})) if travel_request.interests else 'None'}
    - Other moods: {', '.join(list(set(travel_request.mood) - {mood})) if travel_request.mood else 'None'}

    Suggest {GEMINI_SUGGESTED_QUERY_COUNT} diverse and specific search queries (each under 10 words)
    that can be used with Google Places API to find suitable places in {city}
    matching the primary interest '{interest}' and mood '{mood}'.
    The queries should be creative and aim to find unique or interesting places.
    Avoid overly generic queries.

    Return the suggestions as a JSON list of strings. For example:
    ["hidden gem local restaurants for a quiet dinner", "artisanal coffee shops with a cozy vibe"]
    Ensure the output is ONLY the JSON list.
    """
    generation_config = genai.types.GenerationConfig(
        response_mime_type="application/json",
        temperature=0.75  # 창의성을 위해 약간 높임
    )
    try:
        response = model.generate_content(prompt, generation_config=generation_config)
        if response.text:
            suggested_queries = json.loads(response.text)
            if isinstance(suggested_queries, list) and all(isinstance(q, str) for q in suggested_queries):
                logger.info(f"Gemini suggested queries for '{interest}'/'{mood}' in '{city}': {suggested_queries}")
                return suggested_queries
            else:
                logger.warning(f"Gemini returned unexpected format for suggested queries: {response.text}")
                return []
        else:
            logger.warning(
                f"Gemini returned no text for suggested queries (Interest: {interest}, Mood: {mood}, City: {city}).")
            return []
    except json.JSONDecodeError:
        logger.error(
            f"Failed to parse JSON from Gemini suggested queries: {response.text if hasattr(response, 'text') else 'No text in response'}")
        return []
    except Exception as e:
        logger.error(
            f"Error getting search_queries from Gemini (Interest: {interest}, Mood: {mood}, City: {city}): {e}")
        return []


def generate_place(travel_request):
    if not (hasattr(settings, 'GOOGLE_PLACES_API_KEY') and settings.GOOGLE_PLACES_API_KEY):
        logger.error("Google Places API Key is not configured in Django settings.")
        raise ValueError("Google Places API Key is not configured.")

    all_fetched_places = []
    logger.info(f"Starting to fetch real places for TR ID {travel_request.id}...")

    for city in travel_request.cities:
        for interest in travel_request.interests:
            place_types_for_interest = INTEREST_TO_PLACE_TYPE_MAP.get(interest, [])
            for mood in travel_request.mood:
                search_queries_for_combo = []

                # 1. 직접 조합 검색어
                direct_query = f"{mood} {interest}"
                search_queries_for_combo.append({"query": direct_query, "method": "direct_combination"})

                # 2. Gemini 제안 검색어 (선택적, API 호출량 고려)
                if settings.GEMINI_API_KEY:  # Gemini API 키가 있을 때만 시도
                    gemini_suggested = suggest_search_queries_by_gemini(interest, mood, city, travel_request)
                    for g_query in gemini_suggested:
                        search_queries_for_combo.append({"query": g_query, "method": "gemini_suggested"})
                else:
                    logger.info("Skipping Gemini query suggestion as GEMINI_API_KEY is not set.")

                for query_info in search_queries_for_combo:
                    current_query = query_info["query"]
                    search_method = query_info["method"]

                    try:
                        logger.debug(f"Calling find_places_by_text_search for TR ID {travel_request.id}: "
                                     f"query='{current_query}' ({search_method}), city='{city}', type(s)='{place_types_for_interest}', "
                                     )

                        places_found = find_places_by_text_search(
                            query_text=current_query,
                            city_name=city,
                            type_filter=place_types_for_interest,
                            limit=DEFAULT_PLACE_API_LIMIT_PER_QUERY,
                            location=None,
                            radius=None
                        )

                        for place_data in places_found:
                            place_data['searched_interest'] = interest
                            place_data['searched_mood'] = mood
                            place_data['searched_types_by_interest'] = place_types_for_interest
                            place_data['original_search_query'] = current_query  # 실제 사용된 검색어
                            place_data['search_method'] = search_method  # 검색 방식


                        all_fetched_places.extend(places_found)
                        logger.debug(
                            f"Found {len(places_found)} places for query='{current_query}' ({search_method}), city='{city}'")

                    except (ValueError, ConnectionAbortedError, RuntimeError) as e:
                        logger.error(
                            f"API or Config error during Places API call (query: '{current_query}', method: {search_method}, TR ID {travel_request.id}): {e}")
                        pass
                    except Exception as e:
                        logger.error(
                            f"Unexpected error in generate_place (query: '{current_query}', method: {search_method}, TR ID {travel_request.id}): {e}")
                        pass

    logger.info(
        f"Fetched a total of {len(all_fetched_places)} places (before deduplication) for TR ID {travel_request.id}.")

    seen_ids = set()
    unique_places = []
    for place in all_fetched_places:
        pid = place.get("place_id")
        if pid and pid not in seen_ids:
            seen_ids.add(pid)
            unique_places.append(place)
    logger.info(f"Number of unique places found for TR ID {travel_request.id}: {len(unique_places)}")

    if not unique_places:
        logger.warning(f"No unique real places found from Places API for TR ID {travel_request.id}.")
        # ─── 휠체어 진입 가능 필터 적용 ───
        filtered_places = []
        for p in unique_places:
            details = get_place_details_with_wheelchair_info(p["place_id"])
            # details가 None 이면 접근 불가(False/없음)이므로 걸러짐
            if details and details.get("wheelchair_entrance") is True:
                # 원본 p에 추가 정보를 합치고 싶으면 여기서 merge 가능
                p["wheelchair_entrance"] = True
                filtered_places.append(p)
        logger.info(f"Number of wheelchair-accessible places after filter: {len(filtered_places)}")

    places_json = json.dumps(unique_places, ensure_ascii=False)
    return places_json


# generate_travel_schedule_from_gemini 함수는 이전 답변과 동일하게 유지
# (내부에서 generate_place를 호출하고 그 결과를 사용)
def generate_travel_schedule_from_gemini(travel_request):
    if not settings.GEMINI_API_KEY:
        logger.error("Gemini API Key for schedule generation is not configured in settings.")
        raise ValueError("Gemini API Key for schedule generation is not configured.")

    genai.configure(api_key=settings.GEMINI_API_KEY)
    model_name = 'gemini-1.5-flash-latest'
    try:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel(model_name)
    except Exception as e:
        logger.error(f"Failed to initialize Gemini model ({model_name}) for schedule generation: {e}")
        raise RuntimeError(f"Failed to initialize Gemini model for schedule generation: {e}")

    travel_dates = []
    current_date = travel_request.start_date
    while current_date <= travel_request.end_date:
        travel_dates.append(current_date.strftime('%Y-%m-%d'))
        current_date += timedelta(days=1)

    if not travel_dates:
        logger.error(f"Invalid travel period for TravelRequest ID {travel_request.id}: start_date > end_date.")
        raise ValueError("Invalid travel period: Start date must be before or same as end date.")

    try:
        places_json_str = generate_place(travel_request)  # generate_place가 JSON 문자열 반환
    except (ValueError, ConnectionAbortedError, RuntimeError) as e:
        logger.error(f"Failed to generate places for Gemini schedule prompt (TR ID {travel_request.id}): {e}")
        # View에서 이 오류를 잡아서 사용자에게 알리거나, 여기서 기본 오류 JSON 반환
        # raise # View에서 처리하도록 다시 발생시키는 것이 더 좋을 수 있음
        # 또는 Gemini에게 빈 장소 목록을 전달하고 Gemini가 오류 메시지 생성하도록 함
        places_json_str = json.dumps(
            {"schedule_items": [], "error_message": f"Could not retrieve place information: {e}"})

    prompt = f"""
    You are a travel planning assistant.
    Your task is to create a travel itinerary based on the User's Travel Request Details using ONLY the places provided in the "List of Real, Verified Places" below.
    If the "List of Real, Verified Places" is empty or contains too few places to build a meaningful itinerary, you MUST respond with a JSON object containing an empty "schedule_items" list and an "error_message" field explaining that not enough places were found.

    List of Real, Verified Places (fetched from Google Maps API):
    {places_json_str} 

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
    generation_config = genai.types.GenerationConfig(
        response_mime_type="application/json"
    )

    logger.info(f"Sending prompt to Gemini for TR ID {travel_request.id} for schedule generation.")
    try:
        response = model.generate_content(prompt, generation_config=generation_config)

        gemini_response_text = None
        if hasattr(response, 'text') and response.text:
            gemini_response_text = response.text
        elif response.candidates and response.candidates[0].content.parts:
            gemini_response_text = response.candidates[0].content.parts[0].text

        if not gemini_response_text:
            logger.error(f"Gemini schedule response for TR ID {travel_request.id} is empty or unparsable.")
            return json.dumps(
                {"schedule_items": [], "error_message": "AI service failed to generate a schedule response."})

        logger.info(
            f"Received schedule response from Gemini for TR ID {travel_request.id} (first 200 chars): {gemini_response_text[:200]}")
        return gemini_response_text

    except genai.types.generation_types.BlockedPromptException as e:
        logger.error(f"Gemini schedule prompt for TR ID {travel_request.id} was blocked: {e}")
        return json.dumps({"schedule_items": [],
                           "error_message": "Your schedule request could not be processed due to content policy."})
    except Exception as e:
        logger.exception(f"Error calling Gemini API for schedule generation (TR ID {travel_request.id}): {e}")
        return json.dumps({"schedule_items": [],
                           "error_message": f"An unexpected error occurred with the AI scheduling service: {e}"})