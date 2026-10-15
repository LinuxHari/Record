from record.app.auth.service import AuthService
from record.app.auth.password_service import PasswordService
from record.app.auth.jwt_service import JwtService
from record.app.auth.refresh_token_service import RefreshTokenService
from record.app.user.service import UserService
from record.app.user.repository import UserRepository
from record.db.sql.postgres.session import get_pg_context

# Repositories
user_repository = UserRepository(get_pg_context)

# Helper services
password_service = PasswordService()
jwt_service = JwtService()
refresh_token_service = RefreshTokenService()

# Services
auth_service = AuthService(
    user_repository=user_repository,
    password_service=password_service,
    jwt_service=jwt_service,
    refresh_token_service=refresh_token_service,
)
user_service = UserService(user_repository=user_repository)
