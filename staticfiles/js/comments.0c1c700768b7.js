

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.reply-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const commentId = e.currentTarget.dataset.id;
            const form = document.getElementById(`reply-form-${commentId}`);
            if (form) {
                form.classList.toggle('d-none');
                form.querySelector('textarea')?.focus();
            }
        });
    });
});