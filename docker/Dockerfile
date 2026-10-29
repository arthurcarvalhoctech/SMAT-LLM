FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

ARG USER_ID
ARG GROUP_ID
ARG INSTALL_LAYA=false
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu

# 1. Install system dependencies, Java and a *final* Python 3.11.
#
# Ubuntu 22.04's python3.11 package is 3.11.0rc1, which lacks
# sys.get_int_max_str_digits. torch._dynamo's polyfills then fail at import,
# and a later import masks the failure as
# "Duplicate dispatch rule for <built-in function intern>".
# The deadsnakes PPA provides a supported 3.11.x release.
# `gnupg` provides gpg-agent, which add-apt-repository needs to import the PPA key.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        software-properties-common \
        gnupg \
        openjdk-8-jdk \
        maven \
        git \
        curl \
        jq \
        build-essential \
        ca-certificates && \
    add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        python3.11 \
        python3.11-dev \
        python3.11-venv && \
    python3.11 -m ensurepip --upgrade && \
    python3.11 -m pip install --upgrade pip && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 2 && \
    update-alternatives --set python3 /usr/bin/python3.11 && \
    groupadd -g ${GROUP_ID} appuser && \
    useradd -m -u ${USER_ID} -g ${GROUP_ID} appuser && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Fail the build if the interpreter is still the 3.11.0rc1 from Ubuntu 22.04.
RUN python3.11 -c "import sys; sys.get_int_max_str_digits; sys.set_int_max_str_digits"

# 2. Set Environment Variables for Java and Maven
ENV JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
ENV MAVEN_HOME=/usr/share/maven
ENV PATH="$MAVEN_HOME/bin:$JAVA_HOME/bin:$PATH"

WORKDIR /app

# 4. Install Python dependencies
COPY --chown=appuser:appuser SMAT/requirements.txt .
COPY --chown=appuser:appuser SMAT/requirements-laya.txt .
RUN python3 -m pip install --no-cache-dir --upgrade pip && \
    python3 -m pip install --no-cache-dir -r requirements.txt ruff mypy pytest && \
    if [ "$INSTALL_LAYA" = "true" ]; then \
        python3 -m pip install --no-cache-dir torch --index-url "$TORCH_INDEX_URL"; \
        python3 -m pip install --no-cache-dir -r requirements-laya.txt; \
    fi

# Cache Hugging Face weights between runs. Compose mounts a named volume here.
RUN mkdir -p /home/appuser/.cache/huggingface && \
    chown -R appuser:appuser /home/appuser/.cache

USER appuser
CMD ["/bin/bash", "-i"]