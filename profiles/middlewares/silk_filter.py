import logging
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)


class SilkFilterMiddleware(MiddlewareMixin):
    """
    Middleware для фильтрации запросов к Silk
    Помещается ПЕРЕД SilkyMiddleware в MIDDLEWARE
    """
    
    # Расширения файлов которые нужно игнорировать
    IGNORED_EXTENSIONS = (
        '.js', '.css', '.map', '.jpg', '.jpeg', '.png', 
        '.gif', '.svg', '.ico', '.woff', '.woff2', '.ttf', '.eot'
    )
    
    # Префиксы путей которые нужно игнорировать
    IGNORED_PREFIXES = (
        '/static/', '/media/', '/favicon.ico', 
        '/__debug__/', '/admin/jsi18n/'
    )
    
    def process_request(self, request):
        """Помечаем запросы которые нужно игнорировать"""
        path = request.path.lower()
        
        # Проверяем расширение
        if any(path.endswith(ext) for ext in self.IGNORED_EXTENSIONS):
            request._silk_ignore = True
            return None
        
        # Проверяем префикс
        if any(path.startswith(prefix) for prefix in self.IGNORED_PREFIXES):
            request._silk_ignore = True
            return None
        
        return None
    
    def process_response(self, request, response):
        """Можем дополнительно фильтровать по content-type"""
        if hasattr(request, '_silk_ignore'):
            return response
        
        # Игнорируем определенные content-types
        content_type = response.get('Content-Type', '').lower()
        if any(ct in content_type for ct in [
            'javascript', 'css', 'image/', 'font/', 'application/octet-stream'
        ]):
            request._silk_ignore = True
        
        return response