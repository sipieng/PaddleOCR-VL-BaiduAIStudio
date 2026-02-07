import os

import uvicorn
import webbrowser


def main() -> None:
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    webbrowser.open(f"http://{host}:{port}/")
    uvicorn.run("app.server:app", host=host, port=port, reload=True)


if __name__ == "__main__":
    main()
