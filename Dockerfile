FROM fnproject/python:3.11-dev as build-stage

WORKDIR /function

ADD requirements.txt /function/

RUN pip3 install --target /python/ --no-cache --no-cache-dir -r requirements.txt

ADD . /function/

RUN rm -fr /function/.venv /function/__pycache__ ~/.cache/pip /tmp*

FROM fnproject/python:3.11

COPY --from=build-stage /function /function
COPY --from=build-stage /python /python

ENV PYTHONPATH=/python

ENTRYPOINT ["/python/bin/fdk", "/function/func.py", "handler"]
