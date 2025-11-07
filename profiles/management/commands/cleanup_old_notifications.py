from django.core.management.base import BaseCommand
from profiles.management.commands import cleanup_old_notifications

class Command(BaseCommand):
    help = 'Удаляет старые прочитанные уведомления'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Сколько дней хранить уведомления (по умолчанию 30)'
        )

    def handle(self, *args, **options):
        days = options['days']

        if days < 1:
            self.stdout.write(self.style.WARNING('Аргумент --days должен быть больше 0'))
            return

        deleted_count = cleanup_old_notifications(days=days)
        self.stdout.write(self.style.SUCCESS(
            f'✅ Удалено уведомлений: {deleted_count} (старше {days} дней)'
        ))
