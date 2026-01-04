from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from users.models import Profile


__all__ = []


class UserRegistrationTestCase(TestCase):
    """Test user registration functionality"""

    def setUp(self):
        self.client = Client()
        self.signup_url = reverse("users:signup")

    def test_signup_page_loads(self):
        """Test that signup page loads successfully"""
        response = self.client.get(self.signup_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Создать аккаунт")

    def test_valid_registration(self):
        """Test user can register with valid data"""
        data = {
            "username": "testuser",
            "email": "test@example.com",
            "password1": "TestPass123!",
            "password2": "TestPass123!",
            "terms_accepted": True,
        }
        response = self.client.post(self.signup_url, data)
        self.assertEqual(response.status_code, 302)  # Redirect after success

        # Check user was created
        user = User.objects.get(username="testuser")
        self.assertEqual(user.email, "test@example.com")

        # Check profile was created
        self.assertTrue(hasattr(user, "profile"))

    def test_duplicate_username(self):
        """Test registration fails with duplicate username"""
        User.objects.create_user("testuser", "test@example.com", "password")

        data = {
            "username": "testuser",
            "email": "another@example.com",
            "password1": "TestPass123!",
            "password2": "TestPass123!",
            "terms_accepted": True,
        }
        response = self.client.post(self.signup_url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")

    def test_duplicate_email(self):
        """Test registration fails with duplicate email"""
        User.objects.create_user("testuser", "test@example.com", "password")

        data = {
            "username": "newuser",
            "email": "test@example.com",
            "password1": "TestPass123!",
            "password2": "TestPass123!",
            "terms_accepted": True,
        }
        response = self.client.post(self.signup_url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")


class UserLoginTestCase(TestCase):
    """Test user login functionality"""

    def setUp(self):
        self.client = Client()
        self.login_url = reverse("users:login")
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="TestPass123!",
        )
        Profile.objects.get_or_create(user=self.user)

    def test_login_page_loads(self):
        """Test that login page loads successfully"""
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "С возвращением")

    def test_login_with_username(self):
        """Test user can login with username"""
        response = self.client.post(
            self.login_url,
            {
                "username": "testuser",
                "password": "TestPass123!",
            },
        )
        self.assertEqual(response.status_code, 302)  # Redirect after login
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_login_with_email(self):
        """Test user can login with email"""
        response = self.client.post(
            self.login_url,
            {
                "username": "test@example.com",
                "password": "TestPass123!",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_login_with_wrong_password(self):
        """Test login fails with wrong password"""
        response = self.client.post(
            self.login_url,
            {
                "username": "testuser",
                "password": "WrongPassword",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)


class UserProfileTestCase(TestCase):
    """Test user profile functionality"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="TestPass123!",
        )
        self.profile_url = reverse("users:profile")
        self.client.login(username="testuser", password="TestPass123!")

    def test_profile_page_requires_login(self):
        """Test profile page requires authentication"""
        self.client.logout()
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_profile_page_loads(self):
        """Test profile page loads for authenticated user"""
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, 200)

    def test_profile_update(self):
        """Test user can update profile"""
        data = {
            "email": "newemail@example.com",
            "first_name": "Test",
            "last_name": "User",
        }
        response = self.client.post(self.profile_url, data)
        self.assertEqual(response.status_code, 302)

        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "newemail@example.com")
        self.assertEqual(self.user.first_name, "Test")


class PasswordResetTestCase(TestCase):
    """Test password reset functionality"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="TestPass123!",
        )
        self.reset_url = reverse("users:password-reset")

    def test_password_reset_page_loads(self):
        """Test password reset page loads"""
        response = self.client.get(self.reset_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Сброс пароля")

    def test_password_reset_request(self):
        """Test user can request password reset"""
        response = self.client.post(
            self.reset_url,
            {
                "email": "test@example.com",
            },
        )
        self.assertEqual(response.status_code, 302)


class AuthenticationBackendTestCase(TestCase):
    """Test custom authentication backend"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="TestPass123!",
        )
        Profile.objects.get_or_create(user=self.user)

    def test_authenticate_with_username(self):
        """Test authentication with username"""
        from django.contrib.auth import authenticate

        user = authenticate(username="testuser", password="TestPass123!")
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "testuser")

    def test_authenticate_with_email(self):
        """Test authentication with email"""
        from django.contrib.auth import authenticate

        user = authenticate(
            username="test@example.com",
            password="TestPass123!",
        )
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "testuser")

    def test_authenticate_fails_with_wrong_password(self):
        """Test authentication fails with wrong password"""
        from django.contrib.auth import authenticate

        user = authenticate(username="testuser", password="WrongPassword")
        self.assertIsNone(user)
