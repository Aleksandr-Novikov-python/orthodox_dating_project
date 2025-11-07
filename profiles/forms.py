# -*- coding: utf-8 -*-
from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator, MaxValueValidator
from django.utils.safestring import mark_safe
from django.urls import reverse_lazy
from datetime import date, timedelta
import re

from .models import Comment, Complaint, UserProfile, Message, Photo


# ==============================================================================
# ВАЛИДАТОРЫ
# ==============================================================================

def validate_image_size(image):
    """Проверка размера изображения (макс 5MB)"""
    max_size = 5 * 1024 * 1024  # 5MB
    # Проверка, что это файл, а не строка
    if not hasattr(image, 'size'):
        raise ValidationError('Файл изображения не был загружен или повреждён.')

    if image.size > max_size:
        raise ValidationError(f'Размер файла {image.size // (1024 * 1024)}MB превышает допустимые 5MB.')


def validate_city_name(value):
    """Проверка что город содержит только буквы, дефисы и пробелы"""
    if not re.match(r'^[а-яА-ЯёЁa-zA-Z\s\-]+$', value):
        raise ValidationError('Название города должно содержать только буквы')


# ==============================================================================
# ФОРМЫ РЕГИСТРАЦИИ И АУТЕНТИФИКАЦИИ
# ==============================================================================

class UserRegistrationForm(forms.ModelForm):
    """Форма регистрации нового пользователя"""

    password = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите пароль'
        }),
        help_text='Минимум 8 символов, включая буквы и цифры'
    )

    password2 = forms.CharField(
        label='Повторите пароль',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Повторите пароль'
        })
    )

    agree_to_rules = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    class Meta:
        model = User
        fields = ('username', 'first_name', 'email')
        labels = {
            'username': 'Логин',
            'first_name': 'Ваше имя',
            'email': 'Электронная почта'
        }
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Придумайте логин'
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Как вас зовут?'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'your@email.com'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Динамическая генерация ссылки на правила
        rules_url = reverse_lazy('profiles:static_page', kwargs={'slug': 'rules'})
        self.fields['agree_to_rules'].label = mark_safe(
            f'Я прочитал(а) и принимаю <a href="{rules_url}" target="_blank" class="text-primary">Правила сайта</a>'
        )
        self.fields['agree_to_rules'].error_messages = {
            'required': 'Вы должны принять правила сайта для регистрации.'
        }

        # Обязательные поля
        self.fields['first_name'].required = True
        self.fields['email'].required = True

    def clean_username(self):
        """Валидация логина"""
        username = self.cleaned_data.get('username')

        # Проверка длины
        if len(username) < 3:
            raise ValidationError('Логин должен содержать минимум 3 символа')

        # Проверка символов
        if not re.match(r'^[a-zA-Z0-9_-]+$', username):
            raise ValidationError('Логин может содержать только латинские буквы, цифры, дефис и подчёркивание')

        # Проверка на существование
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError('Пользователь с таким логином уже существует')

        return username

    def clean_email(self):
        """Валидация email"""
        email = self.cleaned_data.get('email')

        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError('Этот email уже используется')

        return email.lower()

    def clean_password(self):
        """Валидация пароля"""
        password = self.cleaned_data.get('password')

        try:
            # Используем встроенные валидаторы Django
            validate_password(password)
        except ValidationError as e:
            raise ValidationError(e.messages)

        return password

    def clean_password2(self):
        """Проверка совпадения паролей"""
        password = self.cleaned_data.get('password')
        password2 = self.cleaned_data.get('password2')

        if password and password2 and password != password2:
            raise ValidationError('Пароли не совпадают')

        return password2

    def clean_first_name(self):
        """Валидация имени"""
        name = self.cleaned_data.get('first_name')

        if not re.match(r'^[а-яА-ЯёЁa-zA-Z\s\-]+$', name):
            raise ValidationError('Имя должно содержать только буквы')

        return name.strip().title()


# ==============================================================================
# ФОРМЫ ПРОФИЛЯ
# ==============================================================================

class BaseProfileForm(forms.ModelForm):
    """Базовая форма профиля для переиспользования"""

    class Meta:
        model = UserProfile
        fields = [
            'patronymic', 'date_of_birth', 'gender', 'city', 'photo',
            'about_me', 'height', 'marital_status', 'children',
            'education', 'occupation', 'churching_level',
            'attitude_to_fasting', 'sacraments', 'favorite_saints',
            'spiritual_books',
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control',
                'max': date.today().isoformat()
            }),
            'about_me': forms.Textarea(attrs={
                'rows': 4,
                'class': 'form-control',
                'placeholder': 'Расскажите о себе...',
                'maxlength': 2000
            }),
            'spiritual_books': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control',
                'maxlength': 1000
            }),
            'photo': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Добавляем классы Bootstrap ко всем полям
        for field_name, field in self.fields.items():
            if field_name not in ['photo']:
                if not field.widget.attrs.get('class'):
                    field.widget.attrs['class'] = 'form-control'

    def clean_date_of_birth(self):
        """Валидация даты рождения"""
        dob = self.cleaned_data.get('date_of_birth')

        if not dob:
            return dob

        # Проверка возраста (18-100 лет)
        today = date.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

        if age < 18:
            raise ValidationError('Вам должно быть не менее 18 лет')

        if age > 100:
            raise ValidationError('Проверьте правильность даты рождения')

        # Проверка что дата не в будущем
        if dob > today:
            raise ValidationError('Дата рождения не может быть в будущем')

        return dob

    def clean_city(self):
        """Валидация города"""
        city = self.cleaned_data.get('city')

        if city:
            validate_city_name(city)
            return city.strip().title()

        return city

    def clean_height(self):
        """Валидация роста"""
        height = self.cleaned_data.get('height')

        if height:
            if height < 100 or height > 250:
                raise ValidationError('Укажите корректный рост (100-250 см)')

        return height

    def clean_photo(self):
        """Валидация фото"""
        photo = self.cleaned_data.get('photo')

        if not photo:
            return None 
        # Проверка размера
        validate_image_size(photo)

        # Проверка расширения
        allowed_extensions = ['jpg', 'jpeg', 'png', 'webp']
        ext = photo.name.split('.')[-1].lower()
        if ext not in allowed_extensions:
            raise ValidationError(
                f'Разрешены только изображения: {", ".join(allowed_extensions)}'
            )

        return photo


class UserProfileForm(BaseProfileForm):
    """Форма создания профиля при регистрации"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Обязательные поля для регистрации
        required_fields = ['date_of_birth', 'gender', 'city']
        for field_name in required_fields:
            self.fields[field_name].required = True


class ProfileUpdateForm(BaseProfileForm):
    """Форма редактирования профиля"""
    pass


class UserUpdateForm(forms.ModelForm):
    """Форма обновления данных пользователя"""

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        labels = {
            'first_name': 'Имя',
            'last_name': 'Фамилия',
            'email': 'Email'
        }
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }

    def clean_email(self):
        """Валидация email при обновлении"""
        email = self.cleaned_data.get('email')

        # Проверяем что email не занят другим пользователем
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError('Этот email уже используется другим пользователем')

        return email.lower()

    def clean_first_name(self):
        """Валидация имени"""
        name = self.cleaned_data.get('first_name')

        if name and not re.match(r'^[а-яА-ЯёЁa-zA-Z\s\-]+$', name):
            raise ValidationError('Имя должно содержать только буквы')

        return name.strip().title() if name else name


# ==============================================================================
# ФОРМЫ ФИЛЬТРАЦИИ
# ==============================================================================

class ProfileFilterForm(forms.Form):
    """Форма фильтрации анкет"""

    GENDER_CHOICES = [('', 'Любой')] + list(UserProfile.GENDER_CHOICES)
    CHURCHING_CHOICES = [('', 'Любая')] + list(UserProfile.CHURCHING_LEVEL_CHOICES)

    gender = forms.ChoiceField(
        label='Пол',
        choices=GENDER_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    min_age = forms.IntegerField(
        label='Возраст от',
        min_value=18,
        max_value=99,
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': '18'
        })
    )

    max_age = forms.IntegerField(
        label='Возраст до',
        min_value=18,
        max_value=99,
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': '99'
        })
    )

    city = forms.CharField(
        label='Город',
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Введите город...'
        })
    )

    churching_level = forms.ChoiceField(
        label='Воцерковленность',
        choices=CHURCHING_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def clean(self):
        """Валидация связанных полей"""
        cleaned_data = super().clean()
        min_age = cleaned_data.get('min_age')
        max_age = cleaned_data.get('max_age')

        if min_age and max_age and min_age > max_age:
            raise ValidationError('Минимальный возраст не может быть больше максимального')

        return cleaned_data


# ==============================================================================
# ФОРМЫ СООБЩЕНИЙ И КОММЕНТАРИЕВ
# ==============================================================================

class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ['content']  # ← Должно быть именно 'content'
        widgets = {
            'content': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Введите ваше сообщение...',
                'name': 'content'  # ← Явно указываем name
            })
        }
        labels = {'content': ''}

    def clean_content(self):
        """Валидация содержания сообщения"""
        content = self.cleaned_data.get('content', '').strip()

        if not content:
            raise ValidationError('Сообщение не может быть пустым')

        if len(content) < 1:
            raise ValidationError('Сообщение слишком короткое')

        if len(content) > 2000:
            raise ValidationError('Сообщение слишком длинное (максимум 2000 символов)')

        return content


class CommentForm(forms.ModelForm):
    """Форма добавления комментария"""

    class Meta:
        model = Comment
        fields = ('body',)
        widgets = {
            'body': forms.Textarea(attrs={
                'rows': 4,
                'class': 'form-control',
                'placeholder': 'Оставьте ваш комментарий...',
                'maxlength': 1000
            }),
        }
        labels = {'body': ''}

    def clean_body(self):
        """Валидация комментария"""
        body = self.cleaned_data.get('body', '').strip()

        if not body:
            raise ValidationError('Комментарий не может быть пустым')

        if len(body) < 3:
            raise ValidationError('Комментарий слишком короткий (минимум 3 символа)')

        if len(body) > 1000:
            raise ValidationError('Комментарий слишком длинный (максимум 1000 символов)')

        return body


# ==============================================================================
# ФОРМЫ ФОТО И ЖАЛОБ
# ==============================================================================

class PhotoForm(forms.ModelForm):
    """Форма загрузки фотографии"""

    class Meta:
        model = Photo
        fields = ['image']
        labels = {'image': 'Выберите файл'}
        widgets = {
            'image': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            })
        }

    def clean_image(self):
        """Валидация изображения"""
        image = self.cleaned_data.get('image')

        if image and hasattr(image, 'size'):
            # Проверка размера
            validate_image_size(image)

            # Проверка расширения
            validator = FileExtensionValidator(
                allowed_extensions=['jpg', 'jpeg', 'png', 'webp']
            )
            validator(image)

        return image


class ComplaintForm(forms.ModelForm):
    """Форма подачи жалобы на пользователя"""

    class Meta:
        model = Complaint
        fields = ['reason', 'description']
        labels = {
            'reason': 'Причина жалобы',
            'description': 'Опишите ситуацию подробнее (необязательно)',
        }
        widgets = {
            'reason': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={
                'rows': 5,
                'class': 'form-control',
                'placeholder': 'Опишите подробнее, что произошло...',
                'maxlength': 1000
            }),
        }

    def clean_description(self):
        """Валидация описания жалобы"""
        description = self.cleaned_data.get('description', '').strip()

        if description and len(description) > 1000:
            raise ValidationError('Описание слишком длинное (максимум 1000 символов)')

        return description