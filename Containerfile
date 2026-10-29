FROM registry.access.redhat.com/ubi9/python-314:latest@sha256:ab99fe3dbe49e0dc5bb2b22aee839ba7a673a80db4ee79c6aa2cfb52404ba007 AS builder

WORKDIR /build

COPY --chown=1001:0 pyproject.toml README.md ./
COPY --chown=1001:0 src/ src/

RUN pip wheel --no-cache-dir --wheel-dir /build/wheels .

FROM registry.access.redhat.com/ubi9/python-314-minimal:latest@sha256:bb1dcbb3c9c4146cdb41a2d6910e42d7abe2fa9526d8f12817c03c132b3bcf46

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
