CONSTRAINT_ERRORS = {
    "uq_users_username": {
        "field": "username",
        "issue": "Username not available",
    },
    "uq_users_email": {
        "field": "email",
        "issue": "User with given email already exists",
    },
    "ck_users_username_min_length": {
        "field": "username",
        "issue": "Username is too small",
    },
    "ck_users_email_min_length": {
        "field": "email",
        "issue": "Email address is not valid",
    },
    "ck_users_email_regex_check": {
        "field": "email",
        "issue": "Email address is not valid",
    },
}
