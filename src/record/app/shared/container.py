from record.app.auth.service import AuthService
from record.app.auth.password_service import PasswordService
from record.app.user.service import UserService
from record.app.user.repository import UserRepository
from record.db.sql.postgres.session import get_pg_context

# Repositories
user_repository = UserRepository(get_pg_context)

# Helper services
password_service = PasswordService()

# Services
auth_service = AuthService(user_repository=user_repository, password_service=password_service)
user_service = UserService(user_repository=user_repository)
