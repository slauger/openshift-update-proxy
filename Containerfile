FROM registry.access.redhat.com/ubi9/python-314:latest@sha256:fd506034c95cb5917c80fe480937e1fc17564ab7812f3fded84899ed0cd6e9e4 AS builder

WORKDIR /build

COPY --chown=1001:0 pyproject.toml README.md ./
COPY --chown=1001:0 src/ src/

RUN pip wheel --no-cache-dir --wheel-dir /build/wheels .

FROM registry.access.redhat.com/ubi9/python-314-minimal:latest@sha256:1e4b43488508216fee35b87e6b5425f4ef475eacf9c113f5b901e27af3844fba

LABEL org.opencontainers.image.source="https://github.com/slauger/openshift-update-proxy" \
      org.opencontainers.image.description="Forwarding proxy for OpenShift update resources (Cincinnati API, mirror, release signatures)" \
      org.opencontainers.image.licenses="Apache-2.0"

# apply all pending security updates on top of the (digest-pinned) base image
USER 0
RUN microdnf -y upgrade && \
    microdnf clean all && \
    rm -rf /var/cache/dnf
USER 1001:0

COPY --from=builder --chown=1001:0 /build/wheels /tmp/wheels

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --no-index --find-links /tmp/wheels openshift-update-proxy && \
    rm -rf /tmp/wheels

ENV LISTEN_PORT=5000

EXPOSE 5000

CMD ["openshift-update-proxy"]
