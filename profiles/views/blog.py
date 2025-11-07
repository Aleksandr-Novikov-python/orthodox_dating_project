from django.db.models import Q, Prefetch, Count, Max
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.template.loader import render_to_string
from django.contrib.auth.decorators import login_required

from profiles.forms import CommentForm
from profiles.models import Comment, Post


def post_list(request):
    """Список публикаций"""
    posts = Post.objects.filter(
        status='published'
    ).exclude(
        author__is_superuser=True
    ).select_related('author').annotate(
        comment_count=Count('comments', filter=Q(comments__active=True))
    ).order_by('-created_at')

    return render(request, 'profiles/post_list.html', {'posts': posts})

def post_detail(request, slug):
    """Детали публикации"""
    post = get_object_or_404(
        Post.objects.select_related('author'),
        slug=slug,
        status='published'
    )

    # Получение комментариев с вложенными ответами
    comments = post.comments.filter(
        active=True,
        parent__isnull=True
    ).exclude(
        author__is_superuser=True
    ).select_related('author').prefetch_related(
        Prefetch(
            'replies',
            queryset=Comment.objects.filter(active=True).select_related('author')
        ),
        'likes',
        'dislikes'
    ).order_by('created_at')

    # Обработка нового комментария
    if request.method == 'POST':
        if not request.user.is_authenticated:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': 'Нужно войти, чтобы оставить комментарий.',
                    'auth': False
                }, status=401)

            messages.error(request, 'Нужно войти, чтобы оставить комментарий.')
            return redirect('login')

        comment_form = CommentForm(data=request.POST)
        if comment_form.is_valid():
            # Проверка родительского комментария
            parent_obj = None
            parent_id = request.POST.get('parent_id')
            if parent_id:
                parent_obj = Comment.objects.filter(id=parent_id, post=post).first()

            new_comment = comment_form.save(commit=False)
            new_comment.post = post
            new_comment.author = request.user
            new_comment.parent = parent_obj
            new_comment.active = False  # Премодерация
            new_comment.save()

            # AJAX ответ
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                html = render_to_string(
                    'profiles/includes/comment_item.html',
                    {'comment': new_comment, 'user': request.user}
                )
                return JsonResponse({'success': True})

            messages.success(request, 'Комментарий отправлен на модерациюи появится после проверки.')
            return redirect(post.get_absolute_url())
        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': comment_form.errors
                }, status=400)
    else:
        comment_form = CommentForm()

    return render(request, 'profiles/post_detail.html', {
        'post': post,
        'comments': comments,
        'comment_form': comment_form
    })

@login_required
def like_comment(request, comment_id):
    """Лайк комментария"""
    comment = get_object_or_404(Comment, id=comment_id)

    # Убираем дизлайк если был
    if request.user in comment.dislikes.all():
        comment.dislikes.remove(request.user)

    # Переключаем лайк
    if request.user in comment.likes.all():
        comment.likes.remove(request.user)
    else:
        comment.likes.add(request.user)

    return JsonResponse({
        'likes': comment.total_likes(),
        'dislikes': comment.total_dislikes()
    })

@login_required
def dislike_comment(request, comment_id):
    """Дизлайк комментария"""
    comment = get_object_or_404(Comment, id=comment_id)

    # Убираем лайк если был
    if request.user in comment.likes.all():
        comment.likes.remove(request.user)

    # Переключаем дизлайк
    if request.user in comment.dislikes.all():
        comment.dislikes.remove(request.user)
    else:
        comment.dislikes.add(request.user)

    return JsonResponse({
        'likes': comment.total_likes(),
        'dislikes': comment.total_dislikes()
    })