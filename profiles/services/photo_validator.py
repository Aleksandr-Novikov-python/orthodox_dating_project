"""
Комплексная проверка фотографий при регистрации
Включает: размер, формат, EXIF, качество, дубликаты, обратный поиск
"""
import os
from io import BytesIO
from PIL import Image
from PIL.ExifTags import TAGS
from typing import Tuple, Dict, List
from django.core.files.uploadedfile import UploadedFile


class PhotoValidationError(Exception):
    """Исключение для ошибок валидации фото"""
    pass


class PhotoValidator:
    """Валидатор фотографий для регистрации"""
    
    # Настройки
    MIN_WIDTH = 200
    MIN_HEIGHT = 200
    MAX_WIDTH = 4000
    MAX_HEIGHT = 4000
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    ALLOWED_FORMATS = ['JPEG', 'JPG', 'PNG', 'WEBP']
    MIN_QUALITY_SCORE = 30  # Минимальное качество (0-100)
    
    @classmethod
    def validate_all(cls, image_file, check_internet=False, check_duplicates=True) -> Dict:
        """
        Комплексная проверка фото
        
        Args:
            image_file: загруженный файл
            check_internet: проверять через Google Vision API
            check_duplicates: проверять дубликаты в базе
            
        Returns:
            Dict с результатами проверки
        """
        results = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'checks': {}
        }
        
        try:
            # 1. Проверка базовых параметров
            basic_check = cls.check_basic_requirements(image_file)
            results['checks']['basic'] = basic_check
            if not basic_check['valid']:
                results['valid'] = False
                results['errors'].extend(basic_check['errors'])
            
            # 2. Проверка формата и размеров
            format_check = cls.check_format_and_size(image_file)
            results['checks']['format'] = format_check
            if not format_check['valid']:
                results['valid'] = False
                results['errors'].extend(format_check['errors'])
            
            # 3. Проверка EXIF метаданных
            exif_check = cls.check_exif_metadata(image_file)
            results['checks']['exif'] = exif_check
            results['warnings'].extend(exif_check.get('warnings', []))
            
            # 4. Проверка качества изображения
            quality_check = cls.check_image_quality(image_file)
            results['checks']['quality'] = quality_check
            if not quality_check['valid']:
                results['warnings'].extend(quality_check['warnings'])
            
            # 5. Проверка на дубликаты в базе
            if check_duplicates:
                duplicate_check = cls.check_database_duplicates(image_file)
                results['checks']['duplicates'] = duplicate_check
                if not duplicate_check['valid']:
                    results['valid'] = False
                    results['errors'].extend(duplicate_check['errors'])
            
            # 6. Обратный поиск в интернете
            if check_internet:
                internet_check = cls.check_internet_presence(image_file)
                results['checks']['internet'] = internet_check
                if not internet_check['valid']:
                    results['valid'] = False
                    results['errors'].extend(internet_check['errors'])
            
            return results
            
        except Exception as e:
            results['valid'] = False
            results['errors'].append(f'Ошибка проверки: {str(e)}')
            return results
    
    @classmethod
    def check_basic_requirements(cls, image_file) -> Dict:
        """Проверка базовых требований к файлу"""
        result = {'valid': True, 'errors': []}
        
        try:
            # Проверка наличия файла
            if not image_file:
                result['valid'] = False
                result['errors'].append('Файл не загружен')
                return result
            
            # Проверка размера файла
            if hasattr(image_file, 'size'):
                if image_file.size > cls.MAX_FILE_SIZE:
                    result['valid'] = False
                    result['errors'].append(
                        f'Файл слишком большой ({image_file.size // (1024*1024)}MB). '
                        f'Максимум {cls.MAX_FILE_SIZE // (1024*1024)}MB'
                    )
                
                if image_file.size < 10 * 1024:  # Меньше 10KB
                    result['valid'] = False
                    result['errors'].append('Файл слишком маленький. Минимум 10KB')
            
            # Проверка расширения
            if hasattr(image_file, 'name'):
                ext = os.path.splitext(image_file.name)[1].lower()
                if ext not in ['.jpg', '.jpeg', '.png', '.webp']:
                    result['valid'] = False
                    result['errors'].append(
                        f'Неподдерживаемый формат {ext}. '
                        f'Разрешены: .jpg, .jpeg, .png, .webp'
                    )
            
            return result
            
        except Exception as e:
            result['valid'] = False
            result['errors'].append(f'Ошибка базовой проверки: {str(e)}')
            return result
    
    @classmethod
    def check_format_and_size(cls, image_file) -> Dict:
        """Проверка формата и размеров изображения"""
        result = {'valid': True, 'errors': [], 'info': {}}
        
        try:
            # Открываем изображение
            if hasattr(image_file, 'read'):
                image_file.seek(0)
                img = Image.open(image_file)
                image_file.seek(0)
            else:
                img = Image.open(image_file)
            
            # Сохраняем информацию
            result['info'] = {
                'format': img.format,
                'width': img.width,
                'height': img.height,
                'mode': img.mode
            }
            
            # Проверка формата
            if img.format not in cls.ALLOWED_FORMATS:
                result['valid'] = False
                result['errors'].append(
                    f'Неподдерживаемый формат {img.format}. '
                    f'Разрешены: {", ".join(cls.ALLOWED_FORMATS)}'
                )
            
            # Проверка размеров
            if img.width < cls.MIN_WIDTH or img.height < cls.MIN_HEIGHT:
                result['valid'] = False
                result['errors'].append(
                    f'Изображение слишком маленькое ({img.width}x{img.height}px). '
                    f'Минимум {cls.MIN_WIDTH}x{cls.MIN_HEIGHT}px'
                )
            
            if img.width > cls.MAX_WIDTH or img.height > cls.MAX_HEIGHT:
                result['valid'] = False
                result['errors'].append(
                    f'Изображение слишком большое ({img.width}x{img.height}px). '
                    f'Максимум {cls.MAX_WIDTH}x{cls.MAX_HEIGHT}px'
                )
            
            # Проверка соотношения сторон (для портретов)
            aspect_ratio = img.width / img.height
            if aspect_ratio < 0.5 or aspect_ratio > 2.0:
                result['errors'].append(
                    'Необычное соотношение сторон. Используйте портретное или квадратное фото.'
                )
                result['valid'] = False
            
            return result
            
        except Exception as e:
            result['valid'] = False
            result['errors'].append(f'Ошибка проверки формата: {str(e)}')
            return result
    
    @classmethod
    def check_exif_metadata(cls, image_file) -> Dict:
        """Проверка EXIF метаданных (определение скриншотов/скачанных фото)"""
        result = {'valid': True, 'warnings': [], 'metadata': {}}
        
        try:
            if hasattr(image_file, 'read'):
                image_file.seek(0)
                img = Image.open(image_file)
                image_file.seek(0)
            else:
                img = Image.open(image_file)
            
            # Получаем EXIF данные
            exif_data = img._getexif() if hasattr(img, '_getexif') else None
            
            if exif_data:
                exif = {
                    TAGS.get(tag, tag): value
                    for tag, value in exif_data.items()
                    if tag in TAGS
                }
                result['metadata'] = exif
                
                # Проверка камеры/устройства
                if 'Make' in exif or 'Model' in exif:
                    device = f"{exif.get('Make', '')} {exif.get('Model', '')}".strip()
                    result['metadata']['device'] = device
                
                # Проверка софта для обработки
                if 'Software' in exif:
                    software = exif['Software'].lower()
                    suspicious_software = ['photoshop', 'gimp', 'paint', 'screenshot']
                    
                    if any(word in software for word in suspicious_software):
                        result['warnings'].append(
                            f'⚠️ Фото обработано в {exif["Software"]}. '
                            f'Используйте оригинальное фото.'
                        )
                
                # Проверка даты создания
                if 'DateTime' in exif:
                    result['metadata']['datetime'] = exif['DateTime']
            else:
                # Отсутствие EXIF подозрительно
                result['warnings'].append(
                    '⚠️ Фото не содержит метаданных. '
                    'Возможно, это скриншот или обработанное изображение.'
                )
            
            return result
            
        except Exception as e:
            # Если не удалось прочитать EXIF - не критично
            result['warnings'].append('Не удалось прочитать метаданные фото')
            return result
    
    @classmethod
    def check_image_quality(cls, image_file) -> Dict:
        """Проверка качества изображения (детекция стоковых/низкокачественных фото)"""
        result = {'valid': True, 'warnings': [], 'quality_score': 0}
        
        try:
            if hasattr(image_file, 'read'):
                image_file.seek(0)
                img = Image.open(image_file)
                image_file.seek(0)
            else:
                img = Image.open(image_file)
            
            # Конвертируем в RGB если нужно
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Простая оценка качества
            quality_score = 0
            
            # 1. Проверка резкости (через дисперсию)
            import numpy as np
            img_array = np.array(img)
            
            # Простая оценка резкости
            gray = img.convert('L')
            gray_array = np.array(gray)
            variance = np.var(gray_array)
            
            if variance > 1000:
                quality_score += 40
            elif variance > 500:
                quality_score += 20
            else:
                result['warnings'].append('⚠️ Фото выглядит размытым или низкого качества')
            
            # 2. Проверка насыщенности цветов
            r, g, b = img_array[:,:,0], img_array[:,:,1], img_array[:,:,2]
            color_variance = (np.var(r) + np.var(g) + np.var(b)) / 3
            
            if color_variance > 500:
                quality_score += 30
            elif color_variance > 200:
                quality_score += 15
            
            # 3. Проверка яркости
            brightness = np.mean(gray_array)
            if 50 < brightness < 200:
                quality_score += 30
            else:
                result['warnings'].append('⚠️ Фото слишком тёмное или слишком светлое')
            
            result['quality_score'] = quality_score
            
            if quality_score < cls.MIN_QUALITY_SCORE:
                result['valid'] = False
                result['warnings'].append(
                    f'❌ Качество фото слишком низкое (оценка: {quality_score}/100). '
                    f'Используйте более качественное фото.'
                )
            
            return result
            
        except ImportError:
            # numpy не установлен - пропускаем проверку качества
            result['warnings'].append('Проверка качества недоступна (установите numpy)')
            return result
        except Exception as e:
            result['warnings'].append(f'Не удалось проверить качество: {str(e)}')
            return result
    
    @classmethod
    def check_database_duplicates(cls, image_file) -> Dict:
        """Проверка на дубликаты в базе данных"""
        result = {'valid': True, 'errors': [], 'duplicates': []}
        
        try:
            from profiles.services import verify_photo_originality
            
            # Проверяем дубликаты (без привязки к пользователю при регистрации)
            is_original, photo_hash, similar_photos = verify_photo_originality(
                image=image_file,
                user_profile=None  # При регистрации профиля ещё нет
            )
            
            if not is_original:
                result['valid'] = False
                result['errors'].append(
                    f'❌ Это фото уже используется в системе ({len(similar_photos)} совпадений). '
                    f'Загрузите другое фото.'
                )
                result['duplicates'] = similar_photos
            
            return result
            
        except ImportError:
            result['warnings'] = ['Проверка дубликатов недоступна']
            return result
        except Exception as e:
            result['warnings'] = [f'Ошибка проверки дубликатов: {str(e)}']
            return result
    
    @classmethod
    def check_internet_presence(cls, image_file) -> Dict:
        """Обратный поиск в интернете"""
        result = {'valid': True, 'errors': [], 'matches': []}
        
        try:
            from profiles.services import check_photo_internet
            
            is_unique, message, matches = check_photo_internet(image_file, method='google')
            
            if not is_unique:
                result['valid'] = False
                result['errors'].append(message)
                result['matches'] = matches
            
            return result
            
        except ImportError:
            result['warnings'] = ['Обратный поиск недоступен (Google Vision не настроен)']
            return result
        except Exception as e:
            # Не блокируем регистрацию если API недоступен
            result['warnings'] = [f'Обратный поиск временно недоступен']
            return result


# ✅ Удобная функция для использования в views
def validate_registration_photo(image_file, strict_mode=True) -> Tuple[bool, List[str], List[str]]:
    """
    Быстрая валидация фото при регистрации
    
    Args:
        image_file: загруженный файл
        strict_mode: строгий режим (проверка через Google Vision)
        
    Returns:
        Tuple[bool, List[str], List[str]]: (is_valid, errors, warnings)
        
    Example:
        is_valid, errors, warnings = validate_registration_photo(uploaded_file)
        if not is_valid:
            for error in errors:
                messages.error(request, error)
        for warning in warnings:
            messages.warning(request, warning)
    """
    results = PhotoValidator.validate_all(
        image_file,
        check_internet=strict_mode,  # Google Vision только в строгом режиме
        check_duplicates=True
    )
    
    return results['valid'], results['errors'], results['warnings']
