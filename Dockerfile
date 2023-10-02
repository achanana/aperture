# syntax=docker/dockerfile:1

# Comments are provided throughout this file to help you get started.
# If you need more help, visit the Dockerfile reference guide at
# https://docs.docker.com/engine/reference/builder/

# FROM UBUNTU
# RUN apt-get update && \
#     DEBIAN_FRONTEND=noninteractive apt-get -y install gcc mono-mcs && \
#     rm -rf /var/lib/apt/lists/*

ARG PYTHON_VERSION=3.9.1
FROM python:${PYTHON_VERSION}-slim as base

# Prevents Python from writing pyc files.
ENV PYTHONDONTWRITEBYTECODE=1

# Keeps Python from buffering stdout and stderr to avoid situations where
# the application crashes without emitting any logs due to buffering.
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Create a non-privileged user that the app will run under.
# See https://docs.docker.com/develop/develop-images/dockerfile_best-practices/#user
ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/nonexistent" \
    --shell "/sbin/nologin" \
    --no-create-home \
    --uid "${UID}" \
    appuser

RUN apt-get update && \
    apt-get install -y g++ gcc git cmake
# python3-dev gcc libc-dev
# g++ libc++-dev

# Download dependencies as a separate step to take advantage of Docker's caching.
# Leverage a cache mount to /root/.cache/pip to speed up subsequent builds.
# Leverage a bind mount to requirements.txt to avoid having to copy them into
# into this layer.
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    python -m pip install -r requirements.txt

# ENV CCACHE_DIR=/mnt/ccache

# use ccache (make it appear in path earlier then /usr/bin/gcc etc)
# https://stackoverflow.com/questions/39650056/using-ccache-when-building-inside-of-docker
# RUN for p in gcc g++ cc c++; do ln -vs /usr/bin/ccache /usr/local/bin/$p;  done

RUN git clone --depth=1 https://github.com/opencv/opencv.git && \
    git clone --depth=1 https://github.com/opencv/opencv_contrib

RUN mkdir build

WORKDIR /app/build

# RUN ccache -s

RUN cmake -DOPENCV_ENABLE_NONFREE=ON \
          -DOPENCV_EXTRA_MODULES_PATH=../opencv_contrib/modules \
          -DCMAKE_BUILD_TYPE=RELEASE \
          ../opencv

RUN make -j8 install

# Switch to the non-privileged user to run the application.
USER appuser

WORKDIR .

# Copy the source code into the container.
COPY . .

# Expose the port that the application listens on.
EXPOSE 8000

# Run the application.
CMD python server.py
