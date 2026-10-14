import argparse
from wsgiref.simple_server import make_server

from app.web.application import TheoryWebApplication


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the local economics study website")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    arguments = parser.parse_args()
    application = TheoryWebApplication()
    with make_server(arguments.host, arguments.port, application) as server:
        print(f"Study website listening at http://{arguments.host}:{arguments.port}")
        server.serve_forever()


if __name__ == "__main__":
    main()
