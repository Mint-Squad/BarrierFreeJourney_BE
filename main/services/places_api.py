import time
import logging

import googlemaps
from django.conf import settings
from googlemaps.exceptions import ApiError, Timeout, TransportError # 구체적인 예외 임포트

logger = logging.getLogger(__name__)

try:
    gmaps = googlemaps.Client(key=settings.GOOGLE_PLACES_API_KEY)
except Exception as e:
    logger.error(f"Failed to initialize Google Maps client: {e}")
    gmaps = None

def find_places_by_text_search(
    query_text,
    city_name=None,
    language='ko',
    type_filter=None,
    limit=5,
    max_pages=2,
    location=None,
    radius=None
):
    """
    Text Search API 또는 Nearby Search API를 사용해 실존 장소를 검색
    휠체어 접근성 정보를 포함하고, 접근 불가 장소는 필터링.
    """
    if not settings.GOOGLE_PLACES_API_KEY:
        logger.error("GOOGLE_PLACES_API_KEY is not configured.")
        raise ValueError("Google PLACES API Key is not configured.")

    # 요청할 필드 목록에 wheelchair_accessible_entrance 추가
    base_query_for_logging = query_text  # 로깅용
    all_results = []
    next_token = None
    actual_max_pages: int = min(max_pages, 3)  # API 제한 고려
    for page_num in range(actual_max_pages):
        try:
            if location and radius:
                # Nearby Search
                # Nearby Search는 단일 type만 지원하므로, type_filter가 리스트면 첫 번째 것 사용
                nearby_search_type = None
                if isinstance(type_filter, list) and type_filter:
                    nearby_search_type = type_filter[0]
                elif isinstance(type_filter, str):
                    nearby_search_type = type_filter

                logger.info(
                    f"Calling Google Places Nearby Search:location={location}, radius={radius}, keyword='{query_text}', type='{nearby_search_type}', page_token='{next_token}'")
                response = gmaps.places_nearby(
                    location=location,
                    radius=radius,
                    keyword=query_text,
                    type=nearby_search_type,
                    language=language,
                    page_token=next_token
                )
            else:
                # Text Search
                # Text Search 쿼리에 city_name과 type_filter를 명시적으로 포함
                text_search_query = query_text
                if city_name:
                    text_search_query = f"{text_search_query} in {city_name}"

                # Text Search는 type 파라미터를 직접 받거나, 쿼리에 포함할 수 있음.
                # 여기서는 type 파라미터를 사용. 리스트일 경우 첫 번째 타입 사용.
                text_search_type_param = None
                if isinstance(type_filter, list) and type_filter:
                    text_search_type_param = type_filter[0]  # Text Search도 여러 타입 동시 지원 안 함 (OR 조건은 쿼리에 명시)
                elif isinstance(type_filter, str):
                    text_search_type_param = type_filter

                logger.info(
                    f"Calling Google Places Text Search: query='{text_search_query}', type='{text_search_type_param}', page_token='{next_token}'"
                )
                response = gmaps.places(
                    query=text_search_query,
                    type=text_search_type_param,  # type 파라미터 사용
                    language=language,
                    page_token=next_token
                )
        except ApiError as e:
            logger.error(
                f"Google Maps API Error (page {page_num + 1}) for '{base_query_for_logging}': {e.status} - {e.message}")
            if e.status == "REQUEST_DENIED":
                raise ConnectionAbortedError(
            f"Google Maps API Request Denied: {e.message}. Check API key permissions and billing.")
            break  # API 오류 시 더 이상 페이지 요청 중단
        except Timeout:
            logger.error(f"Google Maps API Timeout (page {page_num + 1}) for '{base_query_for_logging}'.")
            break
        except TransportError as e:
            logger.error(f"Google Maps API Transport Error (page {page_num + 1}) for '{base_query_for_logging}': {e}")
            break
        except Exception as e:  # 기타 예외
            logger.exception(
                f"Unexpected error calling Google Maps API (page {page_num + 1}) for '{base_query_for_logging}': {e}")
            break


        all_results.extend(response.get('results', []))
        next_token = response.get('next_page_token')
        if not next_token or len(all_results) >= limit * actual_max_pages:  # 이미 충분한 결과를 얻었거나 다음 페이지가 없으면 중단
            break

        if page_num < actual_max_pages - 1:  # 마지막 페이지 요청이 아닐 경우에만 sleep
            logger.debug(f"Waiting for next_page_token to activate for query '{base_query_for_logging}'...")
            time.sleep(2)  # next_page_token 활성화 대기 (API 권장 사항)

    processed = []
    fetched_detail_ids=set()
    for place in all_results:
        place_id = place.get('place_id')
        if not place_id:
            continue
        fetched_detail_ids.add(place_id)  # Place Details 호출 전에 추가
        # 상세 정보 호출, 이때 wheelchair_entrance == True인 경우에만 dict 반환
        details = get_place_details_with_wheelchair_info(place_id, language=language)

        if details:
            # detailed_place_info는 이미 필요한 모든 키를 포함하고 있음
            # (place_id, name, lat, lng, address, wheelchair_details 등)
            processed.append(details)

        if len(processed) >= limit:
            break

    logger.info(f"find_places_by_text_search → returned {len(processed)} places for '{base_query_for_logging}'")
    return processed

# Place Details를 호출하여 상세 정보(휠체어 포함)를 가져오는 헬퍼 함수 추가
def get_place_details_with_wheelchair_info(place_id, language='ko'):
    """
    주어진 place_id에 대해 Place Details API를 호출하여 상세 정보와 휠체어 접근성 정보를 가져옵니다.
    """
    if not gmaps:
        logger.error("Google Maps client is not initialized. Cannot perform Place Details search.")
        return None

    # 요청할 필드 목록 정의
    fields = [
        'place_id', 'name', 'formatted_address', 'geometry',  # Basic info
        'wheelchair_accessible_entrance',  # Accessibility
        'type', 'rating', 'opening_hours'  # Additional useful info
    ]
    try:
        logger.info(f"Calling Google Place Details API for place_id: '{place_id}' with fields: {fields}")
        resp = gmaps.place(
            place_id=place_id,
            fields=fields,
            language=language
        )
        result = resp.get('result', {})
        if not result:
            logger.warning(f"No result data from Place Deatils API for place_id '{place_id}'")
            return None

        # 휠체어 접근성 확인
        wheelchair_entrance_accessible = result.get('wheelchair_accessible_entrance')
        if wheelchair_entrance_accessible is False: # 명시적으로 False이면 접근 불가
            logger.info(f"Place '{result.get('name', place_id)}' is not wheelchair accessible (entrance: False).")
            return None # 접근 불가 장소는 None 반환

        details_to_return = {
            "place_id": result.get('place_id'),
            "name": result.get('name'),
            "lat": result.get('geometry', {}).get('location', {}).get('lat'),
            "lng": result.get('geometry', {}).get('location', {}).get('lng'),
            "address": result.get('formatted_address'),
            "types": result.get('types', []),
            "rating": result.get('rating'),
            "website": result.get('website'),
            "opening_hours_text": result.get('opening_hours', {}).get('weekday_text') if result.get(
                'opening_hours') else None,
            # 휠체어 관련 정보는 'wheelchair_details' 키 아래에 그룹화
            "wheelchair_details": {
                "wheelchair_entrance": wheelchair_entrance_accessible,
                # 다른 휠체어 관련 필드(restroom, parking, seating)는 API에서 직접 제공하지 않음
                # 필요하다면 Gemini가 추론하도록 프롬프트에서 안내
            }
        }
        return details_to_return

    except ApiError as e:
        logger.error(f"Google Place Details API Error for place_id '{place_id}': {e.status} - {e.message}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error calling Google Place Details API for place_id '{place_id}': {e}")
        return None