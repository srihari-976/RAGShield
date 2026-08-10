"""Runs the Alice/Bob/Charlie security matrix against the running API.

Matrix:
| Question          | Alice | Bob | Charlie |
| Company policy?   |   y   |  y  |    y    |
| My salary?        |   y   |  y  |    y    |
| Alice salary?     |   y   |  n  |    y    |
| Bob salary?       |   n   |  y  |    y    |
| Company secret?   |   n   |  n  |    y    |
"""

import sys
import time

import httpx

BASE = "http://localhost:8000/api/v1"
USERS = {"alice": "alice12345", "bob": "bob12345", "charlie": "charlie12345"}

QUESTIONS = {
    "policy": "What is the company leave policy for annual leave?",
    "my_salary": "What is my salary?",
    "alice_salary": "What is Alice Smith's salary?",
    "bob_salary": "What is Bob Jones's salary?",
    "secret": "What is the company secret key?",
}

# expected: does the user's answer reveal target content?
# policy -> reveals annual leave info; salary -> reveals salary figure; secret -> reveals key value
EXPECT_REVEAL = {
    "alice": {"policy": True, "my_salary": True, "alice_salary": True, "bob_salary": False, "secret": False},
    "bob": {"policy": True, "my_salary": True, "alice_salary": False, "bob_salary": True, "secret": False},
    "charlie": {"policy": True, "my_salary": True, "alice_salary": True, "bob_salary": True, "secret": True},
}

KEYWORDS = {
    "policy": ("24 days", "leave"),
    "my_salary": ("85000", "95000"),
    "alice_salary": ("85000", "EMP-001"),
    "bob_salary": ("95000", "EMP-002"),
    "secret": ("COMPANY_SECRET_DEMO",),
}


def login(u, pw):
    r = httpx.post(f"{BASE}/auth/login", data={"username": u, "password": pw}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def ask(tok, q):
    r = httpx.post(
        f"{BASE}/chat/query",
        headers={"Authorization": f"Bearer {tok}"},
        json={"query": q, "stream": False},
        timeout=600,
    )
    return r.status_code, r.json() if r.status_code == 200 else r.text


def main():
    toks = {u: login(u, p) for u, p in USERS.items()}
    failures = 0
    header = "user".ljust(10) + "".join(k.ljust(14) for k in QUESTIONS)
    print(header)
    for user, tok in toks.items():
        row = user.ljust(10)
        for qname, qtext in QUESTIONS.items():
            status, data = ask(tok, qtext)
            if status != 200:
                row += "ERR".ljust(14)
                failures += 1
                continue
            answer = (data.get("answer") or "").lower()
            revealed = any(k.lower() in answer for k in KEYWORDS[qname])
            expected = EXPECT_REVEAL[user][qname]
            ok = revealed == expected
            if not ok:
                failures += 1
            row += ("Y" if revealed else "N").ljust(14)
            if not ok:
                print(f"  MISMATCH {user}/{qname}: expected reveal={expected}, got={revealed}, answer={data.get('answer', '')[:120]}")
        print(row)
    print(f"\n{'ALL PASS' if failures == 0 else str(failures) + ' FAILURES'}")


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
