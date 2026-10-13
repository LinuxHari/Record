from record.app.auth.service import AuthService
from record.app.user.service import UserService
from record.app.user.repository import UserRepository
from record.db.sql.postgres.session import get_pg_context

# Repositories
user_repository = UserRepository(get_pg_context)

# Services
auth_service = AuthService(user_repository)
user_service = UserService(user_repository)
