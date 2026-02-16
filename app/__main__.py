import os

import dotenv
import uvicorn
import webbrowser

# 加载 .env 文件
dotenv.load_dotenv()


def main() -> None:
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))

    # 浏览器无法访问 0.0.0.0，自动改为 localhost
    browser_host = "localhost" if host == "0.0.0.0" else host
    webbrowser.open(f"http://{browser_host}:{port}/")

    uvicorn.run("app.server:app", host=host, port=port, reload=True)


if __name__ == "__main__":
    main()
