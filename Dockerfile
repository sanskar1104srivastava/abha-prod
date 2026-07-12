FROM public.ecr.aws/lambda/python:3.12

ARG FUNCTION_MODULE=modules.externalApi.main
ENV FUNCTION_MODULE=${FUNCTION_MODULE}

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common/ common/
COPY modules/ modules/

ENTRYPOINT []
CMD ["sh", "-c", "exec python -m awslambdaric ${FUNCTION_MODULE}.handler"]
