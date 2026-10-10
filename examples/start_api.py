"""Start the local API with environment credentials or secure terminal prompts."""
import sys

if sys.version_info < (3, 11):
    raise SystemExit('Python 3.11+ is required. Use .venv/bin/python.')

import getpass
import os
import socket
import warnings


def main():
    # Avoid prompting for a key if the API port is already occupied.
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', 8000)) == 0:
            raise SystemExit('Port 8000 is already in use. Stop the existing API server first.')
    if not os.environ.get('GEMINI_API_KEY'):
        if not sys.stdin.isatty():
            raise SystemExit('Run in an interactive terminal or set GEMINI_API_KEY first.')
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            try:
                os.environ['GEMINI_API_KEY'] = getpass.getpass('Gemini API key (hidden): ').strip()
            except (getpass.GetPassWarning, EOFError, KeyboardInterrupt):
                raise SystemExit('Secure input unavailable or cancelled. Nothing was saved.') from None
    if not os.environ.get('GEMINI_MODEL'):
        if not sys.stdin.isatty():
            raise SystemExit('Run in an interactive terminal or set GEMINI_MODEL first.')
        try:
            os.environ['GEMINI_MODEL'] = input('Gemini model ID: ').strip()
        except (EOFError, KeyboardInterrupt):
            raise SystemExit('Input cancelled. Nothing was saved.') from None
    if not os.environ['GEMINI_API_KEY'] or not os.environ['GEMINI_MODEL']:
        raise SystemExit('Both API key and model ID are required. Nothing was saved.')
    # Validate the model ID before binding the API port, without a paid call.
    import re
    if not re.fullmatch(r'gemini-[A-Za-z0-9._-]{1,100}', os.environ['GEMINI_MODEL']):
        raise SystemExit('Invalid model ID. Use the gemini-... API model identifier.')
    import uvicorn
    print('Starting API at http://127.0.0.1:8000. Credentials stay in process memory.')
    print('In the web UI, select Gemini API, then Analyze Message. Ctrl+C stops the API.')
    try:
        uvicorn.run('fix_explainer.api:app', host='127.0.0.1', port=8000)
    finally:
        os.environ.pop('GEMINI_API_KEY', None)


if __name__ == '__main__':
    main()
