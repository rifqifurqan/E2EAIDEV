import string

from e2eai.db import ROLE_NAMES
from e2eai.seed import DEMO_DIVISIONS, DEMO_USERS, gen_password


def test_demo_personas_match_the_prd():
    assert DEMO_DIVISIONS == ("Sales", "HR")
    names = {u[0] for u in DEMO_USERS}
    assert names == {"Andi", "Budi", "Intern"}
    by_name = {u[0]: u for u in DEMO_USERS}
    assert by_name["Andi"][2] == "Sales" and by_name["Budi"][2] == "HR"
    assert all(role in ROLE_NAMES for *_, role in DEMO_USERS)  # every seeded role is a real role (FR-F3)
    assert len({u[1] for u in DEMO_USERS}) == len(DEMO_USERS)  # unique emails


def test_generated_password_is_shell_and_dsn_safe():
    allowed = set(string.ascii_letters + string.digits + "-_")  # token_urlsafe alphabet (AGENTS.md rules)
    pw = gen_password()
    assert len(pw) >= 16 and set(pw) <= allowed
    assert gen_password() != gen_password()
