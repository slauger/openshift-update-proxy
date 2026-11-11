FROM registry.access.redhat.com/ubi9/python-314:latest@sha256:628b5a81786b971d1b5e72fb5e45a6b33c498bd71aa66c8539145f68606aaad3 AS builder

WORKDIR /build

COPY --chown=1001:0 pyproject.toml README.md ./
COPY --chown=1001:0 src/ src/

RUN pip wheel --no-cache-dir --wheel-dir /build/wheels .

FROM registry.access.redhat.com/ubi9/python-314-minimal:latest@sha256:5a469f9daa201b92b94ad21049701d99d6257974c5bcc9ec4ab3d39cd6bdf92b

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
