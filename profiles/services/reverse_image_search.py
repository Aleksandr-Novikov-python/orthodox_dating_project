"""
Сервис для обратного поиска изображений
Проверяет, не использует ли пользователь фото из интернета
"""
import os
import io
from typing import Tuple, List, Dict
from django.conf import settings


class ReverseImageSearchService:
    """Сервис обратного поиска изображений"""
    
    @staticmethod
    def search_google_vision(image_file) -> Tuple[bool, List[Dict], str]:
        """
        Поиск изображения через Google Vision API
        
        Args:
            image_file: файл изображения (Django UploadedFile или путь)
            
        Returns:
            Tuple[bool, List[Dict], str]:
                - is_unique: True если фото уникальное (не найдено в интернете)
                - matches: список найденных совпадений
                - error_message: сообщение об ошибке если есть
        """
        try:
            from google.cloud import vision
            from google.oauth2 import service_account
            
            # Инициализация клиента
            credentials_path = getattr(settings, 'GOOGLE_VISION_CREDENTIALS', None)
            
            if credentials_path and os.path.exists(credentials_path):
                credentials = service_account.Credentials.from_service_account_file(
                    credentials_path
                )
                client = vision.ImageAnnotatorClient(credentials=credentials)
            else:
                # Используем переменные окружения
                client = vision.ImageAnnotatorClient()
            
            # Читаем изображение
            if hasattr(image_file, 'read'):
                # Django UploadedFile
                content = image_file.read()
                image_file.seek(0)  # Сбрасываем указатель
            elif isinstance(image_file, str):
                # Путь к файлу
                with io.open(image_file, 'rb') as image_file_obj:
                    content = image_file_obj.read()
            else:
                content = image_file
            
            image = vision.Image(content=content)
            
            # Выполняем поиск похожих изображений
            response = client.web_detection(image=image)
            web_detection = response.web_detection
            
            if response.error.message:
                return False, [], f"API Error: {response.error.message}"
            
            # Анализируем результаты
            matches = []
            
            # Полные совпадения
            if web_detection.full_matching_images:
                for image in web_detection.full_matching_images[:5]:
                    matches.append({
                        'type': 'full_match',
                        'url': image.url,
                        'score': 100
                    })
            
            # Частичные совпадения
            if web_detection.partial_matching_images:
                for image in web_detection.partial_matching_images[:5]:
                    matches.append({
                        'type': 'partial_match',
                        'url': image.url,
                        'score': 80
                    })
            
            # Визуально похожие изображения
            if web_detection.visually_similar_images:
                for image in web_detection.visually_similar_images[:3]:
                    matches.append({
                        'type': 'similar',
                        'url': image.url,
                        'score': 60
                    })
            
            # Страницы с похожими изображениями
            pages = []
            if web_detection.pages_with_matching_images:
                for page in web_detection.pages_with_matching_images[:5]:
                    pages.append({
                        'url': page.url,
                        'title': page.page_title if hasattr(page, 'page_title') else 'Без названия'
                    })
            
            # Добавляем информацию о страницах к совпадениям
            if pages:
                matches.append({
                    'type': 'pages',
                    'pages': pages,
                    'score': 70
                })
            
            # Определяем уникальность
            # Считаем фото неуникальным если есть полные или много частичных совпадений
            full_matches = [m for m in matches if m['type'] == 'full_match']
            partial_matches = [m for m in matches if m['type'] == 'partial_match']
            
            is_unique = len(full_matches) == 0 and len(partial_matches) < 3
            
            return is_unique, matches, ""
            
        except ImportError:
            return False, [], "Google Cloud Vision library not installed. Run: pip install google-cloud-vision"
        except Exception as e:
            return False, [], f"Error: {str(e)}"
    
    @staticmethod
    def search_tineye(image_file) -> Tuple[bool, List[Dict], str]:
        """
        Поиск через TinEye API (требует API ключ)
        
        Args:
            image_file: файл изображения
            
        Returns:
            Tuple[bool, List[Dict], str]: (is_unique, matches, error_message)
        """
        try:
            from pytineye import TinEyeAPIRequest
            
            api_key = getattr(settings, 'TINEYE_API_KEY', None)
            api_url = getattr(settings, 'TINEYE_API_URL', 'https://api.tineye.com/rest/')
            
            if not api_key:
                return False, [], "TinEye API key not configured"
            
            # Инициализация API
            api = TinEyeAPIRequest(api_url, api_key)
            
            # Загружаем изображение
            if hasattr(image_file, 'read'):
                image_data = image_file.read()
                image_file.seek(0)
            elif isinstance(image_file, str):
                with open(image_file, 'rb') as f:
                    image_data = f.read()
            else:
                image_data = image_file
            
            # Выполняем поиск
            response = api.search_data(image_data=image_data)
            
            matches = []
            if response and hasattr(response, 'matches'):
                for match in response.matches[:10]:
                    matches.append({
                        'type': 'tineye_match',
                        'url': match.backlink if hasattr(match, 'backlink') else '',
                        'domain': match.domain if hasattr(match, 'domain') else '',
                        'score': match.score if hasattr(match, 'score') else 100
                    })
            
            is_unique = len(matches) == 0
            
            return is_unique, matches, ""
            
        except ImportError:
            return False, [], "pytineye library not installed. Run: pip install pytineye"
        except Exception as e:
            return False, [], f"TinEye Error: {str(e)}"
    
    @staticmethod
    def format_result_message(is_unique: bool, matches: List[Dict]) -> str:
        """
        Формирует понятное сообщение о результатах проверки
        
        Args:
            is_unique: уникальность изображения
            matches: список совпадений
            
        Returns:
            str: сообщение для пользователя
        """
        if is_unique:
            return "✅ Фотография уникальная, не найдена в интернете."
        
        full_matches = [m for m in matches if m.get('type') == 'full_match']
        partial_matches = [m for m in matches if m.get('type') == 'partial_match']
        
        if full_matches:
            return (
                f"❌ Эта фотография найдена в интернете ({len(full_matches)} точных совпадений). "
                f"Пожалуйста, используйте свою реальную фотографию."
            )
        elif len(partial_matches) >= 3:
            return (
                f"⚠️ Фотография похожа на изображения из интернета ({len(partial_matches)} совпадений). "
                f"Рекомендуем использовать оригинальное фото."
            )
        else:
            return "⚠️ Фотография выглядит подозрительно. Убедитесь, что используете своё настоящее фото."
    
    @classmethod
    def check_photo_originality(cls, image_file, method='google') -> Tuple[bool, str, List[Dict]]:
        """
        Главный метод проверки оригинальности фото
        
        Args:
            image_file: файл изображения
            method: метод проверки ('google', 'tineye')
            
        Returns:
            Tuple[bool, str, List[Dict]]: (is_unique, message, matches)
        """
        if method == 'google':
            is_unique, matches, error = cls.search_google_vision(image_file)
        elif method == 'tineye':
            is_unique, matches, error = cls.search_tineye(image_file)
        else:
            return False, "Неизвестный метод проверки", []
        
        if error:
            # Если ошибка API - разрешаем загрузку но логируем
            print(f"⚠️ Ошибка обратного поиска: {error}")
            return True, "Проверка временно недоступна", []
        
        message = cls.format_result_message(is_unique, matches)
        
        return is_unique, message, matches


# ✅ Удобная функция-обёртка
def check_photo_internet(image_file, method='google') -> Tuple[bool, str, List[Dict]]:
    """
    Быстрая проверка фото на наличие в интернете
    
    Example:
        is_unique, message, matches = check_photo_internet(uploaded_file)
        if not is_unique:
            # Фото найдено в интернете
            print(message)
            for match in matches:
                print(f"Найдено на: {match['url']}")
    """
    return ReverseImageSearchService.check_photo_originality(image_file, method)