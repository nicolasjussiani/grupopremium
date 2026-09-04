import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def main():
    """Instala dependencias e coleta estaticos sem alterar o banco."""
    subprocess.check_call(
        [sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'],
        cwd=BASE_DIR,
    )
    subprocess.check_call(
        [sys.executable, 'manage.py', 'collectstatic', '--noinput', '--clear'],
        cwd=BASE_DIR,
    )


if __name__ == '__main__':
    main()
