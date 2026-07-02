#!/bin/bash
# Lambda entrypoint via the AWS Lambda Web Adapter (docs/decisions.md
# ADR-005) - starts the ordinary Django/gunicorn WSGI app unmodified.
# The adapter (attached as a layer) proxies API Gateway events to this
# process over HTTP on $PORT.

PATH=$PATH:$LAMBDA_TASK_ROOT/bin \
    PYTHONPATH=$PYTHONPATH:/opt/python:$LAMBDA_RUNTIME_DIR \
    exec python -m gunicorn -b=:$PORT -w=1 config.wsgi:application
