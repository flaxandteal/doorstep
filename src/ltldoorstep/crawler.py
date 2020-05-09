import uuid
import json
from autobahn.wamp.exception import ApplicationError
from autobahn.wamp.types import PublishOptions
import logging
import requests
from ltldoorstep.context import DoorstepContext
from ltldoorstep.ini import DoorstepIni
from ltldoorstep.file import make_file_manager
from retry import api as retry_api
import os

ALLOWED_FORMATS = ('CSV', 'GeoJSON')

def ckan_retry(f, **kwargs):
    # runs code until it's successful?
    return retry_api.retry_call(f, fkwargs=kwargs, tries=6, delay=1)

async def do_crawl(component, url, workflow, printer, publish, update=False):
    """
    gets all the datasets on the ckan instance
    """
    # is it worth using datastore to create te client here?
    from ckanapi import RemoteCKAN
    client = RemoteCKAN(url, user_agent='lintol-doorstep-crawl/1.0 (+http://lintol.io)')

    # gets the packages to iterate through using the retry method
    packages = ckan_retry(client.action.package_list)

    for package in packages:
        # creates package metadata
        package_metadata = ckan_retry(client.action.package_show, id=package)

        ini = DoorstepIni(context_package=package_metadata) # classes = studley case
        for resource in ini.package['resources']:
            # checks if the resource is either CSV or geoJson (why geojson but not json?? is it more standarised re: columns)
            if resource['format'] in ALLOWED_FORMATS:
                if workflow:
                    # if workflow is initisialised
                    # creates response oject from the url column
                    r = requests.get(resource['url'])
                    with make_file_manager(content={'data.csv': r.text}) as file_manager:
                        # makes file etc
                        filename = file_manager.get('data.csv')
                        # calls async function to exec the workflow?
                        result = await execute_workflow(component, filename, workflow, ini)
                        print(result)
                        if result:
                            printer.build_report(result)
                if publish:
                    # what is publish in this context?
                    # probably, if there is something to publish that is returned from the component, then do whatevs
                    result = await announce_resource(component, resource, ini, url, update)
            else:
                if not resource['format']:
                    print(resource)
                logging.warn("Not allowed format: {}".format(resource['format']))
    printer.print_output()

async def announce_resource(component, resource, ini, source, update=False):
    """When we join the server, execute the client workflow."""

    if update:
        logging.error("Using force-update")

    component.publish('com.ltldoorstep.event_found_resource', resource['id'], resource, ini.to_dict(), source, update, options=PublishOptions(acknowledge=True))


async def execute_workflow(component, filename, workflow, ini):
    """When we join the server, execute the client workflow.
    Series of instructions to create a report
    """

    #with open(self._filename, 'r') as file_obj:
    #    content = file_obj.read()
    basefilename = os.path.basename(filename)

    with open(workflow, 'r') as file_obj:
        module = file_obj.read()
    workflow = os.path.basename(workflow)

    definitions = {
        str(uuid.uuid4()): DoorstepContext.from_dict({
            'module': workflow
        })
    }
    if not ini:
        ini = DoorstepIni(definitions=definitions)

    if type(ini) is str:
        with open(ini, 'r') as file_obj:
            ini = DoorstepIni.from_dict(json.load(file_obj))
    elif not ini.definitions:
        ini.definitions = definitions

    component._server, component._session = await component.call('com.ltldoorstep.engage')

    await component.call_server('processor.post', {workflow: module}, ini.to_dict())
    content = "file://{}".format(os.path.abspath(filename))

    await component.call_server('data.post', basefilename, content, True)

    try:
        result = await component.call_server('report.get')
    except ApplicationError as e:
        logging.error(e)
        result = None

    result = json.loads(result)
    return result

    #temp commented out
    # if component._printer and result:
        # component._printer.build_report(result)
