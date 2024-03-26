FROM python:3.12 AS build
ADD ./ /data/app/
WORKDIR /data/app/
RUN pip install --no-cache-dir -r requirements.txt
FROM python:3.12-slim
WORKDIR /app

COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=build /data/app .


CMD [ "python3", "./app.py" ]