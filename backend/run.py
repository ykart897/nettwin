import argparse
import os

import uvicorn


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.getenv("NETTWIN_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("NETTWIN_PORT", "8000")))
    args = parser.parse_args()
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=os.getenv("NETTWIN_RELOAD", "1") == "1",
        env_file=".env",
    )
