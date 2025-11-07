from django.shortcuts import render, get_object_or_404
from profiles.models import StaticPage

def home_page(request):
    """Главная страница"""
    return render(request, 'profiles/home.html')

def static_page_view(request, slug):
    """Отображение статической страницы"""
    page = get_object_or_404(StaticPage, slug=slug)
    return render(request, 'profiles/static_page.html', {'page': page})