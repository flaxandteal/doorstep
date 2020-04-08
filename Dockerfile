FROM python:3.7

COPY requirements.txt /

RUN pip3 install -r /requirements.txt

COPY . /doorstep

RUN adduser doorstep

WORKDIR /doorstep

RUN python3 setup.py develop

USER doorstep

ENTRYPOINT [ "/doorstep/run.sh" ]
