import logging
from datetime import datetime

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Max, Count, Subquery, OuterRef
from django.db import IntegrityError, DatabaseError, models
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from profiles.models import Message, Like, Notification, UserSession
from profiles.forms import MessageForm

logger = logging.getLogger(__name__)
User = get_user_model()


class MessagingService:
    """Сервис для работы с сообщениями"""
    
    @staticmethod
    def check_mutual_like(user1, user2):
        """Проверка взаимной симпатии между пользователями"""
        return (
            Like.objects.filter(user_from=user1, user_to=user2).exists() and
            Like.objects.filter(user_from=user2, user_to=user1).exists()
        )
    
    @staticmethod
    def get_user_conversations(user):
        """
        Получить список собеседников пользователя с оптимизацией
        
        Returns:
            QuerySet: пользователи с аннотацией последнего сообщения
        """
        sent_to = Message.objects.filter(
            sender=user,
            is_deleted_by_sender=False
        ).values_list('receiver_id', flat=True)
        
        received_from = Message.objects.filter(
            receiver=user,
            is_deleted_by_receiver=False
        ).values_list('sender_id', flat=True)
        
        interlocutor_ids = set(sent_to) | set(received_from)
        
        return User.objects.filter(
            id__in=interlocutor_ids
        ).select_related('userprofile').annotate(
            last_message_time=Max('sent_messages__timestamp')
        ).order_by('-last_message_time')
    
    @staticmethod
    def get_user_conversations_with_unread(user):
        """
        Получить список собеседников с количеством непрочитанных сообщений
        
        Оптимизировано:
        - Один запрос к БД вместо N+1
        - Использование annotate для подсчёта на уровне БД
        - Subquery для фильтрации только непрочитанных от конкретного собеседника
        
        Returns:
            QuerySet: пользователи с полями last_message_time и unread_count
        """
        # Получаем ID всех собеседников
        sent_to = Message.objects.filter(
            sender=user,
            is_deleted_by_sender=False
        ).values_list('receiver_id', flat=True)
        
        received_from = Message.objects.filter(
            receiver=user,
            is_deleted_by_receiver=False
        ).values_list('sender_id', flat=True)
        
        interlocutor_ids = set(sent_to) | set(received_from)
        
        # Подзапрос для подсчёта непрочитанных сообщений
        unread_subquery = Message.objects.filter(
            sender=OuterRef('pk'),
            receiver=user,
            is_read=False,
            is_deleted_by_receiver=False
        ).values('sender').annotate(
            count=Count('id')
        ).values('count')
        
        # Основной запрос с аннотацией
        return User.objects.filter(
            id__in=interlocutor_ids
        ).select_related(
            'userprofile'
        ).annotate(
            # Время последнего сообщения
            last_message_time=Max('sent_messages__timestamp'),
            # Количество непрочитанных сообщений (один запрос!)
            unread_count=Subquery(unread_subquery, output_field=models.IntegerField())
        ).order_by('-last_message_time')
    
    @staticmethod
    def get_conversation_messages(user, interlocutor):
        """
        Получить сообщения между двумя пользователями
        
        Returns:
            QuerySet: оптимизированный список сообщений
        """
        return Message.objects.filter(
            Q(sender=user, receiver=interlocutor, is_deleted_by_sender=False) |
            Q(sender=interlocutor, receiver=user, is_deleted_by_receiver=False)
        ).select_related(
            'sender', 
            'receiver'
        ).prefetch_related(
            'sender__userprofile'
        ).order_by('timestamp')
    
    @staticmethod
    def mark_messages_as_read(sender, receiver):
        """Отметить входящие сообщения как прочитанные"""
        updated_count = Message.objects.filter(
            sender=sender,
            receiver=receiver,
            is_read=False
        ).update(is_read=True)
        
        if updated_count > 0:
            logger.debug(
                f"Отмечено прочитанными {updated_count} сообщений",
                extra={
                    'sender_id': sender.id,
                    'receiver_id': receiver.id
                }
            )
        
        return updated_count
    
    @staticmethod
    def create_message(sender, receiver, content):
        """
        Создать новое сообщение
        
        Returns:
            Message: созданное сообщение
        """
        message = Message.objects.create(
            sender=sender,
            receiver=receiver,
            content=content
        )
        
        # Обновляем статистику сессии
        try:
            session = UserSession.objects.filter(
                user=sender,
                logout_time__isnull=True
            ).latest('login_time')
            session.messages_sent += 1
            session.save(update_fields=['messages_sent'])
        except UserSession.DoesNotExist:
            logger.debug("Нет активной сессии для обновления статистики")
        
        
        logger.info(
            "Сообщение отправлено",
            extra={
                'sender_id': sender.id,
                'receiver_id': receiver.id,
                'message_id': message.id
            }
        )
        
        return message


@login_required
def inbox(request):
    """
    Список диалогов с оптимизацией запросов
    
    Оптимизировано:
    - Один запрос вместо N+1 для подсчёта непрочитанных сообщений
    - Использование annotate для агрегации на уровне БД
    """
    interlocutors = MessagingService.get_user_conversations_with_unread(
        request.user
    )
    
    logger.debug(
        f"Отображение {len(interlocutors)} диалогов",
        extra={'user_id': request.user.id}
    )
    
    return render(request, 'profiles/inbox.html', {
        'interlocutors': interlocutors
    })


@login_required
def conversation_detail(request, pk):
    """
    Диалог между пользователями с проверками и оптимизацией
    """
    interlocutor = get_object_or_404(User, pk=pk)
    
    # Проверка взаимной симпатии
    if not MessagingService.check_mutual_like(request.user, interlocutor):
        messages.error(request, 'Можно писать только при взаимной симпатии.')
        return redirect('profiles:profile_detail', pk=pk)
    
    # Получение сообщений
    messages_list = MessagingService.get_conversation_messages(
        request.user, 
        interlocutor
    )
    
    # Отметка входящих как прочитанных
    MessagingService.mark_messages_as_read(interlocutor, request.user)
    
    # Обработка отправки сообщения
    if request.method == 'POST':
        return _handle_message_send(request, interlocutor, pk)
    
    form = MessageForm()
    
    return render(request, 'profiles/conversation_detail.html', {
        'interlocutor': interlocutor,
        'messages_list': messages_list,
        'form': form
    })


def _handle_message_send(request, interlocutor, pk):
    """Обработка отправки нового сообщения"""
    content = request.POST.get('content', '').strip()
    
    if not content:
        messages.error(request, 'Сообщение не может быть пустым')
        return redirect('profiles:conversation_detail', pk=pk)
    
    try:
        MessagingService.create_message(
            sender=request.user,
            receiver=interlocutor,
            content=content
        )
        
        messages.success(request, 'Сообщение отправлено!')
        return redirect('profiles:conversation_detail', pk=pk)
        
    except IntegrityError as e:
        # Нарушение ограничений БД (например, удалённый пользователь)
        logger.error(
            f"Ошибка целостности при отправке сообщения: {str(e)}",
            exc_info=True,
            extra={
                'sender_id': request.user.id,
                'receiver_id': interlocutor.id
            }
        )
        messages.error(request, 'Не удалось отправить сообщение. Проверьте доступность получателя.')
        return redirect('profiles:conversation_detail', pk=pk)
        
    except DatabaseError as e:
        # Проблемы с БД
        logger.error(
            f"Ошибка БД при отправке сообщения: {str(e)}",
            exc_info=True,
            extra={
                'sender_id': request.user.id,
                'receiver_id': interlocutor.id
            }
        )
        messages.error(request, 'Ошибка базы данных. Попробуйте позже.')
        return redirect('profiles:conversation_detail', pk=pk)


@login_required
@require_POST
def delete_message_ajax(request, pk):
    """AJAX удаление сообщения с проверкой прав"""
    message = get_object_or_404(Message, pk=pk)
    
    # Проверка прав
    if request.user == message.sender:
        message.is_deleted_by_sender = True
    elif request.user == message.receiver:
        message.is_deleted_by_receiver = True
    else:
        return JsonResponse({
            'success': False,
            'error': 'Недостаточно прав'
        }, status=403)
    
    message.save()
    
    # Полное удаление, если оба удалили
    if message.is_deleted_by_sender and message.is_deleted_by_receiver:
        message.delete()
        logger.info(
            f"Сообщение {pk} удалено обоими пользователями",
            extra={'message_id': pk}
        )
    
    return JsonResponse({'success': True})


@login_required
def get_new_messages(request, pk, last_timestamp):
    """
    AJAX получение новых сообщений для live-обновления
    
    Args:
        pk: ID собеседника
        last_timestamp: ISO-формат последнего известного сообщения
    """
    try:
        interlocutor = get_object_or_404(User, pk=pk)
        
        # Безопасная обработка timestamp
        try:
            last_ts = datetime.fromisoformat(last_timestamp.replace('Z', '+00:00'))
        except ValueError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid timestamp format'
            }, status=400)
        
        # Получение новых сообщений
        messages_qs = Message.objects.filter(
            Q(sender=request.user, receiver=interlocutor, is_deleted_by_sender=False) |
            Q(sender=interlocutor, receiver=request.user, is_deleted_by_receiver=False),
            timestamp__gt=last_ts
        ).select_related('sender').order_by('timestamp')
        
        # Формирование данных
        messages_data = [
            {
                'sender_id': m.sender.id,
                'content': m.content,
                'timestamp': m.timestamp.strftime('%H:%M'),
                'id': m.id
            }
            for m in messages_qs
        ]
        
        new_ts = (
            messages_qs.last().timestamp.isoformat() 
            if messages_qs.exists() 
            else last_timestamp
        )
        
        return JsonResponse({
            'success': True,
            'messages': messages_data,
            'last_timestamp': new_ts
        })
        
    except Exception as e:
        logger.error(
            f"Ошибка получения новых сообщений: {str(e)}",
            exc_info=True,
            extra={
                'user_id': request.user.id,
                'interlocutor_id': pk
            }
        )
        return JsonResponse({
            'success': False,
            'error': 'Internal server error'
        }, status=500)

# class MessagingService:
#     """Сервис для работы с сообщениями"""
    
#     @staticmethod
#     def check_mutual_like(user1, user2):
#         """Проверка взаимной симпатии между пользователями"""
#         return (
#             Like.objects.filter(user_from=user1, user_to=user2).exists() and
#             Like.objects.filter(user_from=user2, user_to=user1).exists()
#         )
    
#     @staticmethod
#     def get_user_conversations(user):
#         """
#         Получить список собеседников пользователя с оптимизацией
        
#         Returns:
#             QuerySet: пользователи с аннотацией последнего сообщения
#         """
#         sent_to = Message.objects.filter(
#             sender=user,
#             is_deleted_by_sender=False
#         ).values_list('receiver_id', flat=True)
        
#         received_from = Message.objects.filter(
#             receiver=user,
#             is_deleted_by_receiver=False
#         ).values_list('sender_id', flat=True)
        
#         interlocutor_ids = set(sent_to) | set(received_from)
        
#         return User.objects.filter(
#             id__in=interlocutor_ids
#         ).select_related('userprofile').annotate(
#             last_message_time=Max('sent_messages__timestamp')
#         ).order_by('-last_message_time')
    
#     @staticmethod
#     def get_conversation_messages(user, interlocutor):
#         """
#         Получить сообщения между двумя пользователями
        
#         Returns:
#             QuerySet: оптимизированный список сообщений
#         """
#         return Message.objects.filter(
#             Q(sender=user, receiver=interlocutor, is_deleted_by_sender=False) |
#             Q(sender=interlocutor, receiver=user, is_deleted_by_receiver=False)
#         ).select_related(
#             'sender', 
#             'receiver'
#         ).prefetch_related(
#             'sender__userprofile'
#         ).order_by('timestamp')
    
#     @staticmethod
#     def mark_messages_as_read(sender, receiver):
#         """Отметить входящие сообщения как прочитанные"""
#         updated_count = Message.objects.filter(
#             sender=sender,
#             receiver=receiver,
#             is_read=False
#         ).update(is_read=True)
        
#         if updated_count > 0:
#             logger.debug(
#                 f"Отмечено прочитанными {updated_count} сообщений",
#                 extra={
#                     'sender_id': sender.id,
#                     'receiver_id': receiver.id
#                 }
#             )
        
#         return updated_count
    
#     @staticmethod
#     def create_message(sender, receiver, content):
#         """
#         Создать новое сообщение
        
#         Returns:
#             Message: созданное сообщение
#         """
#         message = Message.objects.create(
#             sender=sender,
#             receiver=receiver,
#             content=content
#         )
        
#         # Обновляем статистику сессии
#         try:
#             session = UserSession.objects.filter(
#                 user=sender,
#                 logout_time__isnull=True
#             ).latest('login_time')
#             session.messages_sent += 1
#             session.save(update_fields=['messages_sent'])
#         except UserSession.DoesNotExist:
#             logger.debug("Нет активной сессии для обновления статистики")
        
#         # Создаем уведомление
#         Notification.objects.create(
#             recipient=receiver,
#             sender=sender,
#             message=f'Новое сообщение от {sender.first_name or sender.username}.',
#             notification_type='MESSAGE'
#         )
        
#         logger.info(
#             "Сообщение отправлено",
#             extra={
#                 'sender_id': sender.id,
#                 'receiver_id': receiver.id,
#                 'message_id': message.id
#             }
#         )
        
#         return message


# @login_required
# def inbox(request):
#     """Список диалогов с оптимизацией запросов"""
#     interlocutors = MessagingService.get_user_conversations(request.user)
    
#     # Добавляем информацию о непрочитанных сообщениях
#     for interlocutor in interlocutors:
#         interlocutor.unread_count = Message.objects.filter(
#             sender=interlocutor,
#             receiver=request.user,
#             is_read=False
#         ).count()
    
#     return render(request, 'profiles/inbox.html', {
#         'interlocutors': interlocutors
#     })


# @login_required
# def conversation_detail(request, pk):
#     """
#     Диалог между пользователями с проверками и оптимизацией
#     """
#     interlocutor = get_object_or_404(User, pk=pk)
    
#     # Проверка взаимной симпатии
#     if not MessagingService.check_mutual_like(request.user, interlocutor):
#         messages.error(request, 'Можно писать только при взаимной симпатии.')
#         return redirect('profiles:profile_detail', pk=pk)
    
#     # Получение сообщений
#     messages_list = MessagingService.get_conversation_messages(
#         request.user, 
#         interlocutor
#     )
    
#     # Отметка входящих как прочитанных
#     MessagingService.mark_messages_as_read(interlocutor, request.user)
    
#     # Обработка отправки сообщения
#     if request.method == 'POST':
#         return _handle_message_send(request, interlocutor, pk)
    
#     form = MessageForm()
    
#     return render(request, 'profiles/conversation_detail.html', {
#         'interlocutor': interlocutor,
#         'messages_list': messages_list,
#         'form': form
#     })


# def _handle_message_send(request, interlocutor, pk):
#     """Обработка отправки нового сообщения"""
#     content = request.POST.get('content', '').strip()
    
#     if not content:
#         messages.error(request, 'Сообщение не может быть пустым')
#         return redirect('profiles:conversation_detail', pk=pk)
    
#     try:
#         MessagingService.create_message(
#             sender=request.user,
#             receiver=interlocutor,
#             content=content
#         )
        
#         messages.success(request, 'Сообщение отправлено!')
#         return redirect('profiles:conversation_detail', pk=pk)
        
#     except Exception as e:
#         logger.error(
#             f"Ошибка сохранения сообщения: {str(e)}",
#             exc_info=True,
#             extra={
#                 'sender_id': request.user.id,
#                 'receiver_id': interlocutor.id
#             }
#         )
#         messages.error(request, 'Не удалось отправить сообщение')
#         return redirect('profiles:conversation_detail', pk=pk)


# @login_required
# @require_POST
# def delete_message_ajax(request, pk):
#     """AJAX удаление сообщения с проверкой прав"""
#     message = get_object_or_404(Message, pk=pk)
    
#     # Проверка прав
#     if request.user == message.sender:
#         message.is_deleted_by_sender = True
#     elif request.user == message.receiver:
#         message.is_deleted_by_receiver = True
#     else:
#         return JsonResponse({
#             'success': False,
#             'error': 'Недостаточно прав'
#         }, status=403)
    
#     message.save()
    
#     # Полное удаление, если оба удалили
#     if message.is_deleted_by_sender and message.is_deleted_by_receiver:
#         message.delete()
#         logger.info(
#             f"Сообщение {pk} удалено обоими пользователями",
#             extra={'message_id': pk}
#         )
    
#     return JsonResponse({'success': True})


# @login_required
# def get_new_messages(request, pk, last_timestamp):
#     """
#     AJAX получение новых сообщений для live-обновления
    
#     Args:
#         pk: ID собеседника
#         last_timestamp: ISO-формат последнего известного сообщения
#     """
#     try:
#         interlocutor = get_object_or_404(User, pk=pk)
        
#         # Безопасная обработка timestamp
#         try:
#             last_ts = datetime.fromisoformat(last_timestamp.replace('Z', '+00:00'))
#         except ValueError:
#             return JsonResponse({
#                 'success': False,
#                 'error': 'Invalid timestamp format'
#             }, status=400)
        
#         # Получение новых сообщений
#         messages_qs = Message.objects.filter(
#             Q(sender=request.user, receiver=interlocutor, is_deleted_by_sender=False) |
#             Q(sender=interlocutor, receiver=request.user, is_deleted_by_receiver=False),
#             timestamp__gt=last_ts
#         ).select_related('sender').order_by('timestamp')
        
#         # Формирование данных
#         messages_data = [
#             {
#                 'sender_id': m.sender.id,
#                 'content': m.content,
#                 'timestamp': m.timestamp.strftime('%H:%M'),
#                 'id': m.id
#             }
#             for m in messages_qs
#         ]
        
#         new_ts = (
#             messages_qs.last().timestamp.isoformat() 
#             if messages_qs.exists() 
#             else last_timestamp
#         )
        
#         return JsonResponse({
#             'success': True,
#             'messages': messages_data,
#             'last_timestamp': new_ts
#         })
        
#     except Exception as e:
#         logger.error(
#             f"Ошибка получения новых сообщений: {str(e)}",
#             exc_info=True,
#             extra={
#                 'user_id': request.user.id,
#                 'interlocutor_id': pk
#             }
#         )
#         return JsonResponse({
#             'success': False,
#             'error': 'Internal server error'
#         }, status=500)
