from requests.auth import HTTPBasicAuth
import time
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
        openfaas_endpoint = f.read().strip().replace('functions', 'scale-function') # RMV

    data = json.loads(req)

    processor_function = data['function']
    action = data['action']

    if action in ('restart', 'suspend'):
        rq = requests.post(
            f'{openfaas_endpoint}/{processor_function}',
            json={
                'service': processor_function,
                'replicas': 0
            },
            auth=HTTPBasicAuth('admin', openfaas_cred)
        )

        if action == 'restart':
            time.sleep(5)
            rq = requests.post(
                f'{openfaas_endpoint}/{processor_function}',
                json={
                    'service': processor_function,
                    'replicas': 1
                },
                auth=HTTPBasicAuth('admin', openfaas_cred)
            )

        result = {'success': True, 'status': rq.status_code, 'endpoint': openfaas_endpoint}
    else:
        result = {'success': False, 'message': f'Unknown action'}

    return json.dumps(result)
