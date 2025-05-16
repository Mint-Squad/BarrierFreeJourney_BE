import google.generativeai as genai
from django.conf import settings
import json
import logging
# get_place_details_with_wheelchair_info는 find_places_by_text_search 내부에서 사용됨
# gemini_api에서는 find_places_by_text_search와 사용자 선택 장소 처리를 위한 get_place_details_with_wheelchair_info를 임포트
from .places_api import find_places_by_text_search, get_place_details_with_wheelchair_info as get_place_details_from_api
from datetime import timedelta

from ..models.models import Place

# googlemaps 클라이언트는 places_api.py에서 주로 사용되지만, 여기서도 필요시 초기화 가능
# (현재는 get_place_details_from_api가 places_api.py의 gmaps를 사용하므로 직접 필요 없음)

logger = logging.getLogger(__name__)

# INTEREST_TO_PLACE_TYPE_MAP, DEFAULT_PLACE_API_LIMIT_PER_QUERY, GEMINI_SUGGESTED_QUERY_COUNT 등은 이전과 동일
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
DEFAULT_PLACE_API_LIMIT_PER_QUERY = 3
GEMINI_SUGGESTED_QUERY_COUNT = 2  # API 호출 줄이기 위해 1로 유지 또는 조절


def suggest_search_queries_by_gemini(interest, mood, city, travel_request):
    # ... (이전과 동일, 오류 없음) ...
    if not settings.GEMINI_API_KEY:
        logger.error("Gemini API Key for query suggestion is not configured.")
        return []
    try:
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
    Avoid overly generic queries. Prioritize places likely to be wheelchair accessible if possible, but do not explicitly state wheelchair accessibility in the query itself.

    Return the suggestions as a JSON list of strings. For example:
    ["popular local food spots with spacious seating", "art museums with step-free access"]
    Ensure the output is ONLY the JSON list.
    """
    generation_config = genai.types.GenerationConfig(
        response_mime_type="application/json",
        temperature=0.8
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
        else:
            logger.warning(
                f"Gemini returned no text for suggested queries (Interest: {interest}, Mood: {mood}, City: {city}).")
    except json.JSONDecodeError:
        logger.error(
            f"Failed to parse JSON from Gemini suggested queries: {response.text if hasattr(response, 'text') else 'No text in response'}")
    except Exception as e:
        logger.error(
            f"Error getting search_queries from Gemini (Interest: {interest}, Mood: {mood}, City: {city}): {e}")
    return []


def generate_place(travel_request):
    """
    여행 후보지를 생성합니다. places_api.py의 find_places_by_text_search를 사용하므로,
    반환되는 장소들은 이미 wheelchair_entrance가 False가 아닌 것으로 필터링되어 있고,
    기본 정보와 'wheelchair_details' (내부에 'wheelchair_entrance' 포함)를 포함합니다.
    """
    if not (hasattr(settings, 'GOOGLE_PLACES_API_KEY') and settings.GOOGLE_PLACES_API_KEY):
        logger.error("Google Places API Key is not configured in Django settings.")
        raise ValueError("Google Places API Key is not configured.")

    all_candidate_places = []
    # 여러 검색어로 인해 동일 장소가 나올 수 있으므로, 최종적으로 unique한 장소만 반환하기 위해 set 사용
    processed_place_ids_for_this_run = set()
    logger.info(f"Starting to fetch candidate places for TR ID {travel_request.id}...")

    for city in travel_request.cities:
        for interest in travel_request.interests:
            place_types_for_interest = INTEREST_TO_PLACE_TYPE_MAP.get(interest, [])
            for mood in travel_request.mood:
                search_queries_for_combo = []
                direct_query = f"{mood} {interest}"
                search_queries_for_combo.append({"query": direct_query, "method": "direct_combination"})

                if settings.GEMINI_API_KEY:
                    gemini_suggested = suggest_search_queries_by_gemini(interest, mood, city, travel_request)
                    for g_query in gemini_suggested:
                        search_queries_for_combo.append({"query": g_query, "method": "gemini_suggested"})

                for query_info in search_queries_for_combo:
                    current_query = query_info["query"]
                    search_method = query_info["method"]
                    try:
                        logger.debug(
                            f"Finding places for TR ID {travel_request.id}: query='{current_query}' ({search_method}), city='{city}'")

                        # find_places_by_text_search는 이제 휠체어 필터링된 장소 목록 (상세 정보 포함)을 반환
                        places_found_for_current_query = find_places_by_text_search(
                            query_text=current_query,
                            city_name=city,
                            type_filter=place_types_for_interest,
                            limit=DEFAULT_PLACE_API_LIMIT_PER_QUERY,
                            location=None,
                            radius=None
                        )

                        # Add metadata to each place found by this query
                        for place_data in places_found_for_current_query:  # place_data는 이미 상세 정보를 포함
                            place_id = place_data.get('place_id')
                            # 이전에 다른 검색어로 이미 추가된 장소가 아니라면 추가
                            if place_id and place_id not in processed_place_ids_for_this_run:
                                place_data['searched_interest'] = interest
                                place_data['searched_mood'] = mood
                                place_data['searched_types_by_interest'] = place_types_for_interest
                                place_data['original_search_query'] = current_query
                                place_data['search_method'] = search_method
                                all_candidate_places.append(place_data)
                                processed_place_ids_for_this_run.add(place_id)

                        # Save decided place to Place model
                        for p in places_found_for_current_query:
                            Place.objects.update_or_create(place_id=p['place_id'],
                                                           defaults={
                                                               'name': p['name'],
                                                               'address': p['address'],
                                                               'lat': p['lat'],
                                                               'lng': p['lng'],
                                                               'wheelchair_entrance': p.get('wheelchair_details',
                                                                                            {}).get(
                                                                   'wheelchair_entrance')

                                                           })
                        logger.debug(
                            f"Found and processed {len(places_found_for_current_query)} wheelchair-accessible places for query='{current_query}'")

                    except (ValueError, ConnectionAbortedError, RuntimeError) as e:
                        logger.error(
                            f"API or Config error during place search (query: '{current_query}', TR ID {travel_request.id}): {e}")
                        pass  # 개별 검색 실패는 전체를 중단시키지 않음
                    except Exception as e:  # 예상치 못한 다른 에러 (예: KeyError 등)
                        logger.error(
                            f"Unexpected error in generate_place (query: '{current_query}', method: {search_method}, TR ID {travel_request.id}): {e}")
                        pass  # 개별 검색 실패는 전체를 중단시키지 않음

    # all_candidate_places는 이미 unique한 place_id를 가진 장소들로 구성됨 (processed_place_ids_for_this_run 덕분에)
    logger.info(
        f"Generated {len(all_candidate_places)} unique, wheelchair-accessible candidate places for TR ID {travel_request.id}.")

    if not all_candidate_places:
        logger.warning(f"No unique, wheelchair-accessible candidate places found for TR ID {travel_request.id}.")

    # 이전의 불필요한 필터링 로직 제거
    # (find_places_by_text_search가 이미 필터링 및 상세 정보 조회를 완료함)

    places_json = json.dumps(all_candidate_places, ensure_ascii=False)
    return places_json


def get_full_details_for_user_selected_place(place_id, language='ko'):
    """
    사용자가 선택한 place_id에 대해 places_api.get_place_details_from_api를 호출하여
    기본 정보와 휠체어 입구 접근성 정보를 가져옵니다.
    wheelchair_entrance가 False가 아니면 상세 정보를 반환합니다.
    """
    # places_api의 수정된 함수를 직접 호출
    full_details = get_place_details_from_api(place_id, language=language)  # 임포트 시 이름 변경

    if not full_details:  # get_place_details_from_api가 None을 반환하면 (접근 불가 또는 오류)
        logger.warning(
            f"User selected place {place_id} details could not be fetched or is not wheelchair accessible at entrance.")
        return None

    # full_details는 이미 필요한 모든 정보를 포함 (wheelchair_entrance가 False가 아닌 경우)
    return full_details


def generate_travel_schedule_from_gemini(travel_request):
    if not settings.GEMINI_API_KEY:
        logger.error("Gemini API Key for schedule generation is not configured.")
        raise ValueError("Gemini API Key for schedule generation is not configured.")

    model_name = 'gemini-1.5-flash-latest'
    try:
        if not genai.get_model(model_name):
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
        logger.error(f"Invalid travel period for TR ID {travel_request.id}")
        raise ValueError("Invalid travel period.")

    user_selected_place_ids_raw = list(
                travel_request.selected_places.values_list('place_id', flat=True)
        )
    mandatory_places_info = []
    if user_selected_place_ids_raw:
        logger.info(
            f"Processing {len(user_selected_place_ids_raw)} user selected place_ids for TR ID {travel_request.id}")
        for place_id in user_selected_place_ids_raw:
            full_detailed_info = get_full_details_for_user_selected_place(place_id)
            if full_detailed_info:
                mandatory_places_info.append(full_detailed_info)
            # else: 로깅은 get_full_details_for_user_selected_place 내부에서 처리

    logger.info(
        f"Found {len(mandatory_places_info)} mandatory (user-selected, wheelchair entrance accessible) places for TR ID {travel_request.id}.")

    additional_candidate_places_for_schedule = []
    try:
        candidate_places_json_str = generate_place(travel_request)
        all_candidate_places_from_generate_place = json.loads(candidate_places_json_str)

        mandatory_ids_set = {p['place_id'] for p in mandatory_places_info}
        additional_candidate_places_for_schedule = [
            p for p in all_candidate_places_from_generate_place if p['place_id'] not in mandatory_ids_set
        ]
        logger.info(
            f"Prepared {len(additional_candidate_places_for_schedule)} additional candidate places for TR ID {travel_request.id}.")
    except Exception as e:  # 좀 더 포괄적인 예외 처리
        logger.error(f"Failed to generate or process additional candidate places for TR ID {travel_request.id}: {e}")

    if not mandatory_places_info and not additional_candidate_places_for_schedule:
        logger.warning(
            f"No mandatory places and no additional candidates for TR ID {travel_request.id}. Cannot generate schedule.")
        return json.dumps({"schedule_items": [],
                           "error_message": "휠체어 접근 가능한 장소를 찾을 수 없어 일정을 생성할 수 없습니다. 선택한 장소를 확인하거나 여행 요청을 수정해주세요."})

    mandatory_places_for_prompt_str = json.dumps(mandatory_places_info, ensure_ascii=False)
    additional_candidates_for_prompt_str = json.dumps(additional_candidate_places_for_schedule, ensure_ascii=False)

    # ... (generate_travel_schedule_from_gemini 함수 상단은 동일) ...

    prompt = f"""
        You are a meticulous and thoughtful travel planning assistant specializing in wheelchair-accessible itineraries.
        Create a detailed, accessible itinerary for the user’s trip, balancing 2–3 main activities per day, ensuring variety and a good distribution of activities throughout the entire travel period, including evenings.

        User Travel Request:
        - Country: {travel_request.country}
        - Cities: {', '.join(travel_request.cities)}
        - Dates: {travel_dates[0]} to {travel_dates[-1]} (Available days for scheduling: {', '.join(travel_dates)})
        - Interests: {', '.join(travel_request.interests) or 'None'}
        - Mood: {', '.join(travel_request.mood) or 'None'}
        - Transport: {', '.join(travel_request.transportation) or 'None'}

        1) **Mandatory Places** (must include all of these. Each place object includes "place_id", "name", "lat", "lng", "address", "types", "rating", "website", "opening_hours_text", and "wheelchair_details" which contains "wheelchair_entrance" (guaranteed to be not False)):
        {mandatory_places_for_prompt_str}

        2) **Additional Candidate Places** (Consider these to enrich the schedule if "Mandatory Places" are few or to fill gaps. These also include full details similar to Mandatory Places, with "wheelchair_details" confirming "wheelchair_entrance" is not False. **Avoid selecting places from this list if they are already in the "Mandatory Places" list.** Aim for variety.):
        {additional_candidates_for_prompt_str}

        **Key Instructions for Itinerary Creation:**
        1.  **Wheelchair Accessibility is Paramount:**
            -   ALL scheduled places MUST be suitable for wheelchair users. The provided lists are pre-filtered so "wheelchair_details.wheelchair_entrance" is NOT false.
            -   The "wheelchair_details" key in each place object currently only confirms "wheelchair_entrance". For other facilities (restrooms, parking, seating), you may need to make reasonable inferences based on place "types" (e.g., a 'museum' or 'shopping_mall' is more likely to have accessible restrooms than a small 'store'). Clearly state if information beyond entrance accessibility is an assumption or if "wheelchair_details.wheelchair_entrance" was null (meaning unknown, not confirmed false).
        2.  **Incorporate User's Selected Places:** Integrate all "Mandatory Places" naturally into the itinerary.
        3.  **Utilize Additional Candidates Wisely:** If "Mandatory Places" are few, or to enrich the schedule, select suitable and **diverse** places from "Additional Candidate Places". Do not simply repeat places already selected by the user.
        4.  **Balanced Schedule Across Full Duration:**
            -   Distribute activities evenly from the start_date to the end_date.
            -   Ensure the **last day (end_date)** also has appropriate activities, perhaps lighter ones or those conveniently located, considering the end of the trip.
        5.  **Include Evening Activities:**
            -   **Crucially, plan for activities or dining options for the evenings (e.g., approximately 18:00 - 21:00 or later if appropriate for the place type and city).**
            -   These evening places must also be wheelchair accessible and fit the user's interests and mood if possible. Consider restaurants, scenic spots for night views, or relaxed evening entertainment.
        6.  **Pacing and Variety:** Aim for a comfortable pace, typically 2-3 main activities per day, with adequate time for travel and rest. Mix types of activities based on user interests.
        7.  **Logical Flow and Minimized Travel:** Group nearby attractions. Suggest efficient, accessible routes.
        8.  **Single Visit Principle:** Each distinct place should ideally be visited only once during the entire trip.
        9.  **Transportation:** Suggest appropriate wheelchair-friendly transportation.

        **Output Format:**
        The entire response MUST be a single valid JSON object.
        The JSON object MUST have a key "schedule_items" which is a list of schedule item objects.
        Each schedule item object MUST contain:
        -   "place_id": string (from the provided lists)
        -   "place_name": string (from the provided lists)
        -   "date": string (YYYY-MM-DD format, within the travel period)
        -   "start_time": string (HH:MM format, e.g., "10:00")
        -   "end_time": string (HH:MM format, e.g., "12:00")
        -   "lat": float (latitude from the provided lists)
        -   "lng": float (longitude from the provided lists)
        -   "address": string (full address from the provided lists)
        -   "transport_type": string

        If a meaningful, accessible itinerary cannot be formed, "schedule_items" should be an empty list, and you MUST include an "error_message" field.

        Example of a single schedule item:
        {{
            "place_id": "ChIJ...",
            "place_name": "Example Museum",
            "date": "{travel_dates[0] if travel_dates else 'YYYY-MM-DD'}",
            "start_time": "10:00",
            "end_time": "12:30",
            "lat": 37.12345,
            "lng": 127.12345,
            "address": "123 Example Street, Seoul",
            "transport_type": "accessible taxi",
            "description": "Explore modern art exhibits.",
            "wheelchair_accessibility_notes": "Wheelchair entrance: True. Accessible restrooms are typically available in large museums."
        }}

        Generate a plausible, enjoyable, and fully wheelchair-accessible itinerary.
    """
    # ... (이하 Gemini API 호출 및 응답 처리 로직은 이전과 동일) ...
    # ... (이하 Gemini API 호출 및 응답 처리 로직은 이전과 동일) ...
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

        try:
            parsed_response = json.loads(gemini_response_text)
            if "schedule_items" not in parsed_response:
                logger.error(
                    f"Gemini response for TR ID {travel_request.id} is missing 'schedule_items' key. Response: {gemini_response_text[:500]}")
                return json.dumps({"schedule_items": [], "error_message": "AI 서비스가 반환한 일정 형식이 올바르지 않습니다."})
        except json.JSONDecodeError:
            logger.error(
                f"Failed to parse JSON from Gemini schedule response for TR ID {travel_request.id}. Response: {gemini_response_text[:500]}")
            return json.dumps({"schedule_items": [], "error_message": "AI 서비스가 반환한 일정 정보를 처리할 수 없습니다."})

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
