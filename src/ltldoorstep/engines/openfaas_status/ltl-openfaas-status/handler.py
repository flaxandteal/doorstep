from requests.auth import HTTPBasicAuth
import json
import requests

def handle(req):
    """handle a request to the function
    Args:
        req (str): request body
    """

    with open('/var/openfaas/secrets/authentication-secret', 'r') as f:
        openfaas_cred = f.read().strip()

    with open('/var/openfaas/secrets/openfaas-endpoint', 'r') as f:
        openfaas_endpoint = f.read().strip()

    rq = requests.get(
        openfaas_endpoint,
        json={
        },
        auth=HTTPBasicAuth('admin', openfaas_cred)
    )

    content = json.loads(rq.content)

    fns = [
        {
            'name': fn['name'],
            'available': fn['availableReplicas'],
            'total': fn['replicas'],
        }
        for fn in content
    ]

    return json.dumps(fns)
