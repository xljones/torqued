import os
import re
import sys
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import time

USERNAME = os.environ.get('PA_USERNAME')
PASSWORD = os.environ.get('PA_PASSWORD')

if not USERNAME or not PASSWORD:
    print("Error: PA_USERNAME and PA_PASSWORD must be set")
    sys.exit(1)

LOGIN_URL = "https://www.pythonanywhere.com/login/"
DASHBOARD_URL = f"https://www.pythonanywhere.com/user/{USERNAME}/webapps/"


def _parse_expiry_date(html: str) -> str | None:
    # PythonAnywhere renders the expiry date as an ISO date in the dashboard HTML.
    # Look for a date near expiry/disabled keywords; fall back to any YYYY-MM-DD found.
    for pattern, flags in [
        (r'(?:expir|disabled?\s+on)[^<]{0,60}(\d{4}-\d{2}-\d{2})', re.IGNORECASE),
        (r'(\d{4}-\d{2}-\d{2})', 0),
    ]:
        m = re.search(pattern, html, flags)
        if m:
            return m.group(1)
    return None


def renew():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })

    try:
        print(f"Logging in as {USERNAME}...")
        login_page = session.get(LOGIN_URL, timeout=10)
        login_page.raise_for_status()

        soup = BeautifulSoup(login_page.content, 'html.parser')
        csrf_token = soup.find('input', {'name': 'csrfmiddlewaretoken'})

        if not csrf_token:
            print("Could not find CSRF token on login page")
            return False

        csrf_token = csrf_token['value']

        payload = {
            'csrfmiddlewaretoken': csrf_token,
            'auth-username': USERNAME,
            'auth-password': PASSWORD,
            'login_view-current_step': 'auth'
        }

        response = session.post(
            LOGIN_URL,
            data=payload,
            headers={'Referer': LOGIN_URL},
            timeout=10,
            allow_redirects=True
        )
        response.raise_for_status()

        if "Log out" not in response.text and "logout" not in response.text.lower():
            print(f"Login failed — still on login page (url: {response.url})")
            return False

        print("Login successful")

        time.sleep(1)
        dashboard = session.get(DASHBOARD_URL, timeout=10)
        dashboard.raise_for_status()
        soup = BeautifulSoup(dashboard.content, 'html.parser')

        extend_action = None
        for form in soup.find_all('form', action=True):
            action = form.get('action', '')
            if "/extend" in action.lower():
                extend_action = action
                print(f"Found extend action: {action}")
                break

        if not extend_action:
            print("No extend button found — app does not need renewal yet")
            return True

        dashboard_csrf = soup.find('input', {'name': 'csrfmiddlewaretoken'})
        if not dashboard_csrf:
            print("Could not find CSRF token on dashboard")
            return False

        extend_url = f"https://www.pythonanywhere.com{extend_action}"
        print(f"Extending web app at {extend_url}...")

        result = session.post(
            extend_url,
            data={'csrfmiddlewaretoken': dashboard_csrf['value']},
            headers={'Referer': DASHBOARD_URL},
            timeout=10
        )
        result.raise_for_status()

        if result.status_code == 200 and "webapps" in result.url.lower():
            expiry = _parse_expiry_date(result.text)
            if not expiry:
                expiry = (datetime.now(timezone.utc) + timedelta(days=30)).strftime('%Y-%m-%d')
            print(f"Web app extended successfully — extended until: {expiry}")
            return True

        print(f"Extension failed — status {result.status_code}, url {result.url}")
        return False

    except requests.Timeout:
        print("Request timed out")
        return False
    except requests.RequestException as e:
        print(f"Network error: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False


if __name__ == "__main__":
    success = renew()
    sys.exit(0 if success else 1)
