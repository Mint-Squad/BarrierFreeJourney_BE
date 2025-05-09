# main/services/places_api_service.py
import googlemaps
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


def find_places_by_text_search(query_text, city_name=None, language='ko'):
    """
    주어진 쿼리 텍스트를 사용하여 Google Maps Places API (Text Search)를 호출합니다.
    city_name이 제공되면 쿼리에 추가하여 검색 지역을 한정합니다.
    """
    if not settings.GOOGLE_MAPS_API_KEY:
        logger.error("GOOGLE_MAPS_API_KEY is not configured.")
        raise ValueError("Google Maps API Key is not configured.")

    gmaps = googlemaps.Client(key=settings.GOOGLE_MAPS_API_KEY)

    # 검색 쿼리에 도시 이름 추가 (선택 사항이지만 정확도 향상에 도움)
    search_query = f"{query_text} in {city_name}" if city_name else query_text

    try:
        logger.info(f"Searching Google Places API with query: '{search_query}'")
        # Text Search 사용 (gmaps.places가 Text Search 역할을 함)
        places_result = gmaps.places(query=search_query, language=language)

        processed_results = []
        for place in places_result.get('results', []):
            # 필수 정보 확인
            name = place.get('name')
            google_place_id = place.get('place_id')
            location = place.get('geometry', {}).get('location', {})
            lat = location.get('lat')
            lng = location.get('lng')

            if not all([name, google_place_id, lat is not None, lng is not None]):
                logger.warning(f"Skipping place due to missing essential data: {name or 'Unknown name'}")
                continue

            processed_results.append({
                'place_name': name,
                'google_place_id': google_place_id,
                'lat': lat,
                'lng': lng,
                'address': place.get('formatted_address', '주소 정보 없음'),
                'types': place.get('types', []),
                'rating': place.get('rating'),
                # 필요한 다른 정보 추가 가능 (예: photos, opening_hours 등 - 추가 API 호출 필요할 수 있음)
            })

        logger.info(f"Found {len(processed_results)} places for query: '{search_query}'")
        return processed_results  # 검색된 장소 리스트 반환

    except googlemaps.exceptions.ApiError as e:
        logger.error(f"Google Maps API Error for query '{search_query}': {e}")
        raise ConnectionError(f"Google Maps API Error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error calling Google Maps Places API for query '{search_query}': {e}")
        raise ConnectionError(f"Unexpected error with Google Maps service: {e}")