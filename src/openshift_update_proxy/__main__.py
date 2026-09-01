"""Entry point running the application with waitress."""

import logging

from waitress import serve

from openshift_update_proxy.app import create_app
from openshift_update_proxy.config import Config


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    config = Config()
    app = create_app(config)

    logging.getLogger("openshift-update-proxy").info(
        "listening on %s:%d", config.listen_host, config.listen_port
    )
    serve(app, host=config.listen_host, port=config.listen_port)


if __name__ == "__main__":
    main()
