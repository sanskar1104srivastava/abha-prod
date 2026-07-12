FROM public.ecr.aws/lambda/python:3.12

WORKDIR /var/task

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -t .

COPY common common
COPY modules modules

CMD ["modules.dataFlow.main.handler"]
