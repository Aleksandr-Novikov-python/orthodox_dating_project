# -*- coding: utf-8 -*-
from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)

class ProfilesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'profiles'
    verbose_name = 'Профили пользователей'

    def ready(self):
        import profiles.signals.profile_signals
        import profiles.signals.handle_like_notification_signal
        import profiles.signals.handle_new_message_notification_signal
        import profiles.signals.session_signals
        import profiles.signals.complaint_signal
        import profiles.signals.create_user_profile_signal
        import profiles.signals.photo_signals

