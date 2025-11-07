from django.test import TestCase, Client
from django.contrib.auth import get_user_model

User = get_user_model()

class ProfileViewsTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )

    def test_profile_list_accessible(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get('/profiles/')
        self.assertEqual(response.status_code, 200)

    def test_profile_list_has_pagination(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get('/profiles/')
        self.assertIn('page_obj', response.context)