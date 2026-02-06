import os

import dotenv


dotenv.load_dotenv()


def getenv_required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


class Settings:
    def __init__(self) -> None:
        self.baidu_api_url = (
            os.getenv("BAIDU_PADDLE_OCR_API_URL", "").strip().strip('"')
        )
        self.baidu_job_url = (
            os.getenv("BAIDU_PADDLE_OCR_JOB_URL", "").strip().strip('"')
        )
        self.baidu_token = os.getenv("BAIDU_AI_STUDIO_API_KEY", "").strip().strip('"')

        self.output_root = os.getenv("OUTPUT_ROOT", "output").strip().strip('"')
        self.max_file_bytes = int(os.getenv("MAX_FILE_BYTES", str(25 * 1024 * 1024)))
        self.max_total_bytes = int(os.getenv("MAX_TOTAL_BYTES", str(250 * 1024 * 1024)))
        self.default_concurrency = int(os.getenv("DEFAULT_CONCURRENCY", "2"))

    def validate(self) -> None:
        if not self.baidu_token:
            raise RuntimeError("Missing BAIDU_AI_STUDIO_API_KEY in environment")
        # API URLs are optional depending on sync/async usage.


settings = Settings()
