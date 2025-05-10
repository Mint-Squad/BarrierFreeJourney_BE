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
    """
    if not settings.GOOGLE_PLACES_API_KEY:
        logger.error("GOOGLE_PLACES_API_KEY is not configured.")
        raise ValueError("Google PLACES API Key is not configured.")

    # 기본 검색 쿼리 생성
    search_query = f"{query_text} in {city_name}" if city_name else query_text

    all_results = []
    next_token = None
    actual_max_pages = min(max_pages, 3)  # API 제한 고려
    for page_num in range(actual_max_pages):
        try:
            if location and radius:
                logger.info(
                    f"Calling Google Places Nearby Search:location={location}, radius={radius}, keyword='{search_query}', type='{type_filter}', page_token='{next_token}'")
                res = gmaps.places_nearby(
                    location=location,
                    radius=radius,
                    keyword=search_query,
                    type=type_filter,
                    language=language,
                    page_token=next_token
                )
            else:
                logger.info(
                    f"Calling Google Places Text Search: query='{search_query}', type='{type_filter}', page_token='{next_token}'")
                response = gmaps.places(
                    query=search_query,
                    language=language,
                    page_token=next_token
                )
        except ApiError as e:
            logger.error(
                f"Google Maps API Error (page {page_num + 1}) for '{search_query}': {e.status} - {e.message}")
            if e.status == "REQUEST_DENIED":
                raise ConnectionAbortedError(
            f"Google Maps API Request Denied: {e.message}. Check API key permissions and billing.")
            break  # API 오류 시 더 이상 페이지 요청 중단
        except Timeout:
            logger.error(f"Google Maps API Timeout (page {page_num + 1}) for '{search_query}'.")
            break
        except TransportError as e:
            logger.error(f"Google Maps API Transport Error (page {page_num + 1}) for '{search_query}': {e}")
            break
        except Exception as e:  # 기타 예외
            logger.exception(
                f"Unexpected error calling Google Maps API (page {page_num + 1}) for '{search_query}': {e}")
            break


        all_results.extend(response.get('results', []))
        next_token = response.get('next_page_token')
        if not next_token or len(all_results) >= limit * actual_max_pages:  # 이미 충분한 결과를 얻었거나 다음 페이지가 없으면 중단
            break

        if page_num < actual_max_pages - 1:  # 마지막 페이지 요청이 아닐 경우에만 sleep
            logger.debug(f"Waiting for next_page_token to activate for query '{search_query}'...")
            time.sleep(2)  # next_page_token 활성화 대기 (API 권장 사항)

    processed = []
    for place in all_results:
        name = place.get('name')
        place_id = place.get('place_id')
        loc = place.get('geometry', {}).get('location', {})
        lat = loc.get('lat')
        lng = loc.get('lng')
        if not all([name, place_id, lat is not None, lng is not None]):
            logger.warning(f"Skipping incomplete place: {name}")
            continue

        processed.append({
            "place_name": name,
            "place_id": place_id,
            "lat": lat,
            "lng": lng,
            "address": place.get('formatted_address', '주소 정보 없음'),
            "types": place.get('types', []),
            "rating": place.get('rating'),
        })
        if len(processed) >= limit:
            break

    logger.info(f"find_places_by_text_search → returned {len(processed)} places for '{search_query}'")
    return processed
