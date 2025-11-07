from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse

from profiles.models import Notification

@login_required
def notification_list(request):
    notifications = Notification.objects.filter(
        recipient=request.user
    ).select_related('sender').order_by('-created_at')

    unread_count = notifications.filter(is_read=False).count()

    return render(request, 'profiles/notifications.html', {
        'notifications': notifications,
        'unread_count': unread_count
    })

@login_required
def mark_all_notifications_read(request):
    if request.method == 'POST':
        updated = Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return JsonResponse({'status': 'success', 'updated': updated})
    return JsonResponse({'error': 'Invalid method'}, status=405)