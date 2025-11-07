import json
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import User
from .models import Message
from channels.db import database_sync_to_async

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.interlocutor_id = self.scope['url_route']['kwargs']['pk']
        self.user = self.scope['user']

        user_ids = sorted([int(self.user.id), int(self.interlocutor_id)])
        self.room_group_name = f'chat_{user_ids[0]}_{user_ids[1]}'

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        # Отметить входящие сообщения как прочитанные
        await self.mark_messages_as_read()

        # Отправить историю сообщений
        history = await self.get_message_history()
        for msg in reversed(history):
            await self.send(text_data=json.dumps({
                'message': msg['content'],
                'sender_id': msg['sender_id'],
                'timestamp': msg['timestamp'].strftime('%H:%M'),
                'file_url': msg['file_url']
            }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message_content = text_data_json.get('message', '')
        file_data = text_data_json.get('file', None)  # предполагается, что файл передаётся как base64 или URL

        new_message = await self.save_message(message_content, file_data)

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': new_message.content,
                'sender_id': new_message.sender.id,
                'timestamp': new_message.timestamp.strftime('%H:%M'),
                'file_url': new_message.file.url if new_message.file else None
            }
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'message': event['message'],
            'sender_id': event['sender_id'],
            'timestamp': event['timestamp'],
            'file_url': event.get('file_url')
        }))

    @database_sync_to_async
    def save_message(self, message_content, file_data=None):
        interlocutor = User.objects.get(id=self.interlocutor_id)
        new_msg = Message(sender=self.user, receiver=interlocutor, content=message_content)

        if file_data:
            # Здесь нужно реализовать сохранение файла (например, из base64 или URL)
            # new_msg.file.save(...) — зависит от формата file_data
            pass

        new_msg.save()
        return new_msg

    @database_sync_to_async
    def get_message_history(self, limit=50):
        interlocutor = User.objects.get(id=self.interlocutor_id)
        messages = Message.objects.filter(
            sender__in=[self.user, interlocutor],
            receiver__in=[self.user, interlocutor]
        ).order_by('-timestamp')[:limit]

        return [
            {
                'sender_id': msg.sender.id,
                'content': msg.content,
                'timestamp': msg.timestamp,
                'file_url': msg.file.url if msg.file else None
            }
            for msg in messages
        ]

    @database_sync_to_async
    def mark_messages_as_read(self):
        interlocutor = User.objects.get(id=self.interlocutor_id)
        Message.objects.filter(
            sender=interlocutor,
            receiver=self.user,
            is_read=False
        ).update(is_read=True)
