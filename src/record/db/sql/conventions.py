from sqlalchemy import MetaData

convention = {
    # Unique Constraints
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    
    # Foreign Key Constraints
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    
    # Check Constraints (e.g., age > 18)
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    
    # Indexes (Non-unique performance lookups)
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    
    # Primary Keys
    "pk": "pk_%(table_name)s"
}

metadata = MetaData(naming_convention=convention)