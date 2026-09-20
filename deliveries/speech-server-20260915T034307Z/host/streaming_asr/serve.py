"""Run existing speech-service plus the K7 streaming route."""
import argparse
import importlib.util
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--service-dir', type=Path, required=True)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    root = args.service_dir.resolve()
    sys.path.insert(0, str(root))
    os.chdir(root)
    from dotenv import load_dotenv
    load_dotenv(root / '.env')
    spec = importlib.util.spec_from_file_location('k7_existing_speech', root / 'main.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from fastapi.middleware.cors import CORSMiddleware
    origins = os.getenv('K7_FRONTEND_ORIGINS', 'http://10.3.3.68:3000').split(',')
    module.app.add_middleware(CORSMiddleware,
        allow_origins=[origin.strip() for origin in origins if origin.strip()],
        allow_methods=['GET','POST'], allow_headers=['Content-Type'])
    from host.streaming_asr.gateway import mount_streaming_asr
    mount_streaming_asr(module.app)
    import uvicorn
    uvicorn.run(module.app, host=args.host, port=args.port, access_log=False,
                ws_max_size=4096, ws_max_queue=4)


if __name__ == '__main__':
    main()
