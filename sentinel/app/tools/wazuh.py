import requests
from requests.auth import HTTPBasicAuth
import os

def get_wazuh_alerts():
    url = f"{os.getenv('WAZUH_API_URL')}/security/user/authenticate"
    
    token = requests.get(
        url,
        auth=HTTPBasicAuth(
            os.getenv("WAZUH_USER"),
            os.getenv("WAZUH_PASS")
        ),
        verify=False
    ).json()["data"]["token"]

    headers = {"Authorization": f"Bearer {token}"}

    alerts = requests.get(
        f"{os.getenv('WAZUH_API_URL')}/alerts",
        headers=headers,
        verify=False
    ).json()

    return alerts