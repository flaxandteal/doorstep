# Lintol Doorstep

This is a tool within the Lintol system.

## Installation

We recommend `pipenv`, but any `setuptools` compatible install method should work.

    pipenv shell
    python3 -m pip install -r requirements.txt

Or, for development,

    pipenv shell
    python3 -m pip install -r requirements-development.txt
    python3 setup.py develop

## Example

From the project root directory.

    ltldoorstep process tests/examples/data/protected_wrecks.geojson src/ltldoorstep_examples/boundary_checker_impr.py  -e dask.threaded

## Running tests

    python3 -m pytest tests

## Experimenting with HTTP mode

Start the `doorstep` server:

    ltldoorstep serve --engine dask.threaded --protocol http

The following `curl` command, run in the root of the `doorstep-examples` folder runs the boundary-checker against some sample data.

    SESSION=$(curl -s -q -X POST -H "Content-Type: multipart/form-data" -F "module=lintol/boundary-checker/processor.py" -F 'ini={"definitions": {"boundary-checker": {"module": "boundary-checker", "settings": {"boundary": "$->ni"}, "supplementary": {"ni": {"location": "tests/data/osni-ni-outline-lowres.geojson", "source": "OSNI"}}}}};type=application/json' http://localhost:5000/processor | jq -r '._session'); echo $SESSION; curl -i -X POST -H "Content-Type: multipart/form-data" -F "_session=$SESSION" -F "content=@tests/data/protected_wrecks.geojson;type=application/geojson;filename=protected_wrecks.geojson" http://localhost:5000/data; (curl "http://localhost:5000/report?_session=$SESSION" | jq)

## Example Processors

    A processor is a function that runs a specific check or validation against data. Several examples are included within the doorstep repository, in the `ltldoorstep_examples` module - these are:

Check out the `lintol/doorstep-examples` repository for examples.

### Boundary Checker

This takes in JSON files and checks all the points are within a particular boundary. You can test it against `test/examples/data/protected_wrecks.geojson`.

### CSV Checker

This takes CSV data and checks the data records are valid - ie, no duplicates, valid IDs.
Can be tested against `test/examples/data/bad.csv`.

### CSV Lint 

This outputs the CSV file. Can be tested against `test/examples/data/dispensing-by-contractor-june-2018.csv`

### Classify File

A processor to categorise the file based on the location information. 

To test use `ltldoorstep process tests/examples/data/register-countries.json src/ltldoorstep_examples/dt_classify_location.py -e dask.threaded`

### Good

Outputs data in a tabular format. Run the test for this using `tests/examples/data/awful.csv`

### PII 

Processor to find any personally identifiable information within the data. This can be tested using `test/examples/data/pii.csv`

### Registers 

The data is checked against the open data the government has for location information on gov.uk. Can be tested using `tests/examples/data/register-statistical-geography.csv`

### Timetable Checker

The data is checked to see if it is specific to Northern Ireland. This can be tested against `test/examples/data/ni-hpi-by-property-type_package.json`
