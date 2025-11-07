"""
Сервис для проверки оригинальности фотографий
Использует imagehash для определения дубликатов
"""
import io
import imagehash
from PIL import Image
from io import BytesIO
from django.core.files.uploadedfile import InMemoryUploadedFile
from profiles.models import Photo
from typing import Tuple, Optional


class PhotoVerificationService:
    """Сервис для проверки фото на дубликаты"""
    
    @staticmethod
    def find_similar_photos(photo_hash, user_profile, exclude_photo_id=None, threshold=5):
        """
        Ищет похожие фото у пользователя
        
        Args:
            photo_hash: хеш для сравнения
            user_profile: профиль пользователя
            exclude_photo_id: ID фото для исключения
            threshold: порог различия (0-20, меньше = строже)
        
        Returns:
            list: [(Photo, similarity_score), ...]
        """
        from profiles.models import Photo
        
        # Получаем все фото пользователя с хешами
        query = Photo.objects.filter(
            user_profile=user_profile,
            image_hash__isnull=False
        )
        
        if exclude_photo_id:
            query = query.exclude(id=exclude_photo_id)
        
        similar_photos = []
        target_hash = imagehash.hex_to_hash(photo_hash)
        
        for photo in query:
            try:
                existing_hash = imagehash.hex_to_hash(photo.image_hash)
                difference = target_hash - existing_hash
                
                if difference <= threshold:
                    similar_photos.append((photo, difference))
            except Exception:
                continue
        
        # Сортируем по похожести (меньше = более похоже)
        similar_photos.sort(key=lambda x: x[1])
        
        return similar_photos


# ✅ Удобные функции-обёртки для быстрого использования

def verify_photo_originality(image_input, user_profile, exclude_photo_id=None):
    """
    Проверяет оригинальность фото
    
    Args:
        image_input: bytes, file-like object или путь к файлу
        user_profile: профиль пользователя
        exclude_photo_id: ID фото для исключения из поиска
    
    Returns:
        tuple: (is_original, photo_hash, similar_photos)
    
    ✅ Работает с любым типом хранилища
    """
    # Вычисляем хеш
    photo_hash = calculate_photo_hash(image_input)
    
    # Ищем похожие фото
    similar = PhotoVerificationService.find_similar_photos(
        photo_hash=photo_hash,
        user_profile=user_profile,
        exclude_photo_id=exclude_photo_id
    )
    
    is_original = len(similar) == 0
    
    return is_original, photo_hash, similar


def calculate_photo_hash(image_input):
    """
    Вычисляет perceptual hash изображения
    
    Args:
        image_input: может быть:
            - bytes (содержимое файла)
            - file-like object (BytesIO, FieldFile и т.д.)
            - str (путь к файлу - для обратной совместимости)
    
    Returns:
        str: хеш изображения в виде строки
    
    ✅ Работает с локальным хранилищем И облачными (S3, GCS и т.д.)
    """
    try:
        # Случай 1: bytes
        if isinstance(image_input, bytes):
            image = Image.open(io.BytesIO(image_input))
        
        # Случай 2: file-like object (имеет метод read)
        elif hasattr(image_input, 'read'):
            image_data = image_input.read()
            # Если read() вернул не bytes, а file-like, читаем еще раз
            if hasattr(image_data, 'read'):
                image_data = image_data.read()
            image = Image.open(io.BytesIO(image_data))
        
        # Случай 3: строка (путь к файлу) - для обратной совместимости
        elif isinstance(image_input, str):
            image = Image.open(image_input)
        
        else:
            raise ValueError(f"Неподдерживаемый тип входных данных: {type(image_input)}")
        
        # Конвертируем в RGB если нужно
        if image.mode not in ('RGB', 'L'):
            image = image.convert('RGB')
        
        # Вычисляем perceptual hash
        hash_value = imagehash.average_hash(image, hash_size=8)
        
        return str(hash_value)
        
    except Exception as e:
        raise ValueError(f"Ошибка вычисления хеша изображения: {e}")

def find_photo_duplicates(user_profile) -> list:
    """
    Найти все дубликаты фото у пользователя
    
    Example:
        duplicates = find_photo_duplicates(user.userprofile)
    """
    service = PhotoVerificationService()
    photos = Photo.objects.filter(user_profile=user_profile)
    
    duplicates = []
    for photo in photos:
        if photo.image_hash:
            similar = service.find_similar_photos(
                photo.image_hash,
                user_profile=user_profile,
                exclude_photo_id=photo.id
            )
            if similar:
                duplicates.append((photo, similar))
    
    return duplicates
