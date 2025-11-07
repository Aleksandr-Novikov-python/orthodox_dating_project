"""
Команда для массовой проверки фотографий на дубликаты

Использование:
    python manage.py verify_photos                    # Проверить все фото
    python manage.py verify_photos --user-id 123      # Проверить фото пользователя
    python manage.py verify_photos --update-hashes    # Обновить хеши
    python manage.py verify_photos --delete-duplicates  # Удалить дубликаты
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from profiles.models import Photo, UserProfile
from profiles.services import PhotoVerificationService

User = get_user_model()


class Command(BaseCommand):
    help = 'Проверка фотографий на оригинальность и дубликаты'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='ID пользователя для проверки'
        )
        parser.add_argument(
            '--update-hashes',
            action='store_true',
            help='Обновить хеши для всех фото'
        )
        parser.add_argument(
            '--delete-duplicates',
            action='store_true',
            help='УДАЛИТЬ найденные дубликаты (осторожно!)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Режим тестирования (не изменять БД)'
        )

    def handle(self, *args, **options):
        user_id = options.get('user_id')
        update_hashes = options.get('update_hashes')
        delete_duplicates = options.get('delete_duplicates')
        dry_run = options.get('dry_run')
        
        # Получаем queryset
        queryset = Photo.objects.select_related('user_profile__user')
        
        if user_id:
            try:
                user = User.objects.get(id=user_id)
                queryset = queryset.filter(user_profile__user=user)
                self.stdout.write(f"🔍 Проверка фото пользователя: {user.username}")
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'❌ Пользователь с ID {user_id} не найден'))
                return
        else:
            self.stdout.write("🔍 Проверка всех фотографий в системе")
        
        total = queryset.count()
        self.stdout.write(f"📊 Всего фотографий: {total}")
        
        # Обновление хешей
        if update_hashes:
            self.stdout.write("\n" + "="*50)
            self.stdout.write("🔢 Обновление хешей...")
            self._update_hashes(queryset, dry_run)
        
        # Поиск дубликатов
        self.stdout.write("\n" + "="*50)
        self.stdout.write("🔍 Поиск дубликатов...")
        stats = self._find_duplicates(queryset)
        
        # Удаление дубликатов
        if delete_duplicates and stats['duplicates']:
            self.stdout.write("\n" + "="*50)
            if dry_run:
                self.stdout.write(self.style.WARNING("⚠️ Режим DRY-RUN: дубликаты НЕ будут удалены"))
            else:
                self.stdout.write(self.style.WARNING("🗑️ УДАЛЕНИЕ ДУБЛИКАТОВ..."))
            self._delete_duplicates(stats['duplicates'], dry_run)
        
        # Итоги
        self.stdout.write("\n" + "="*50)
        self.stdout.write(self.style.SUCCESS("✅ Проверка завершена!"))
        self._print_summary(stats)

    def _update_hashes(self, queryset, dry_run):
        """Обновление хешей для фото"""
        calculated = 0
        skipped = 0
        errors = 0
        
        photos_without_hash = queryset.filter(image_hash__isnull=True) | queryset.filter(image_hash='')
        total = photos_without_hash.count()
        
        self.stdout.write(f"📝 Фото без хеша: {total}")
        
        for i, photo in enumerate(photos_without_hash, 1):
            try:
                if not photo.photo:
                    errors += 1
                    continue
                
                # Вычисляем хеш
                from profiles.services import calculate_photo_hash
                photo_hash = calculate_photo_hash(photo.photo.path)
                
                if not dry_run:
                    photo.image_hash = photo_hash
                    photo.save(update_fields=['image_hash'])
                
                calculated += 1
                
                if i % 10 == 0:
                    self.stdout.write(f"  Обработано: {i}/{total}", ending='\r')
                
            except Exception as e:
                errors += 1
                self.stdout.write(self.style.ERROR(f"\n  ❌ Ошибка для фото {photo.id}: {e}"))
        
        self.stdout.write(f"\n✅ Вычислено: {calculated} | ⚠️ Ошибок: {errors}")

    def _find_duplicates(self, queryset):
        """Поиск дубликатов"""
        checked = 0
        duplicates_data = []
        errors = 0
        
        total = queryset.count()
        
        for i, photo in enumerate(queryset, 1):
            try:
                if not photo.image_hash:
                    continue
                
                similar = PhotoVerificationService.find_similar_photos(
                    photo_hash=photo.image_hash,
                    user_profile=photo.user_profile,
                    exclude_photo_id=photo.id
                )
                
                checked += 1
                
                if similar:
                    duplicates_data.append({
                        'photo': photo,
                        'similar': similar
                    })
                
                if i % 10 == 0:
                    self.stdout.write(f"  Проверено: {i}/{total}", ending='\r')
                
            except Exception as e:
                errors += 1
        
        self.stdout.write(f"\n✅ Проверено: {checked} | ❌ С дубликатами: {len(duplicates_data)} | ⚠️ Ошибок: {errors}")
        
        # Показываем детали дубликатов
        if duplicates_data:
            self.stdout.write("\n📋 Детали дубликатов:")
            for item in duplicates_data[:10]:  # Первые 10
                photo = item['photo']
                similar = item['similar']
                self.stdout.write(
                    f"  📸 Фото #{photo.id} ({photo.user_profile.user.username}): "
                    f"найдено {len(similar)} похожих"
                )
        
        return {
            'checked': checked,
            'duplicates': duplicates_data,
            'errors': errors
        }

    def _delete_duplicates(self, duplicates_data, dry_run):
        """Удаление дубликатов"""
        deleted = 0
        kept = 0
        
        # Группируем по хешам для удаления
        hash_groups = {}
        
        for item in duplicates_data:
            photo = item['photo']
            similar = item['similar']
            
            # Собираем все фото с одинаковым хешем
            if photo.image_hash not in hash_groups:
                hash_groups[photo.image_hash] = []
            
            hash_groups[photo.image_hash].append(photo)
            for sim_photo, score in similar:
                if sim_photo not in hash_groups[photo.image_hash]:
                    hash_groups[photo.image_hash].append(sim_photo)
        
        # Для каждой группы оставляем самое старое
        for photo_hash, photos in hash_groups.items():
            if len(photos) <= 1:
                continue
            
            # Сортируем по дате (старые первыми)
            photos.sort(key=lambda p: p.uploaded_at)
            
            # Оставляем первое
            kept_photo = photos[0]
            kept += 1
            
            self.stdout.write(
                f"  📌 Оставлено: Фото #{kept_photo.id} "
                f"({kept_photo.user_profile.user.username}, "
                f"{kept_photo.uploaded_at.strftime('%d.%m.%Y')})"
            )
            
            # Удаляем остальные
            for photo in photos[1:]:
                if not dry_run:
                    photo.delete()
                deleted += 1
                self.stdout.write(
                    f"    🗑️ Удалено: Фото #{photo.id} "
                    f"({photo.user_profile.user.username}, "
                    f"{photo.uploaded_at.strftime('%d.%m.%Y')})"
                )
        
        if dry_run:
            self.stdout.write(self.style.WARNING(f"\n⚠️ DRY-RUN: Было бы удалено {deleted} дубликатов"))
        else:
            self.stdout.write(self.style.SUCCESS(f"\n✅ Удалено: {deleted} дубликатов"))

    def _print_summary(self, stats):
        """Вывод итоговой статистики"""
        self.stdout.write("\n📊 ИТОГОВАЯ СТАТИСТИКА:")
        self.stdout.write(f"  ✅ Проверено фотографий: {stats['checked']}")
        self.stdout.write(f"  ❌ Найдено дубликатов: {len(stats['duplicates'])}")
        self.stdout.write(f"  ⚠️ Ошибок: {stats['errors']}")