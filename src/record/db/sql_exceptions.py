class SqlException(Exception):
    """Base class for SQL exceptions."""
    pass

class SqlIntegrityException(SqlException):
    """Raised when a SQL integrity error occurs."""
    pass

class SqlNoResultException(SqlException):
    """Raised when no records are found in the database."""
    pass
