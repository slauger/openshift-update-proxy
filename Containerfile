FROM registry.access.redhat.com/ubi9/python-314:latest@sha256:015ebf0ddb86cd25d28ac1c2c82ef4ef3c8c9a650dd1b217502534436087ea79 AS builder

WORKDIR /build

COPY --chown=1001:0 pyproject.toml README.md ./
COPY --chown=1001:0 src/ src/

RUN pip wheel --no-cache-dir --wheel-dir /build/wheels .

FROM registry.access.redhat.com/ubi9/python-314-minimal:latest@sha256:30a3131dd35d3af85092047a9ad8cd5b292563a6755332be4d35ac73f3559b11

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
