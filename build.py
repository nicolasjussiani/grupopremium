import os
import subprocess
import sys

def main():
    print("Starting build process...")
    
    # 1. Install dependencies
    print("Installing dependencies...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--break-system-packages", "-r", "requirements.txt"])
    except subprocess.CalledProcessError:
        print("Fallback: trying with uv pip...")
        try:
            subprocess.check_call(["uv", "pip", "install", "--system", "-r", "requirements.txt"])
        except Exception as e:
            print(f"Failed to install dependencies: {e}")
            sys.exit(1)

    # 2. Run migrations
    print("Running database migrations...")
    try:
        subprocess.check_call([sys.executable, "manage.py", "migrate", "--noinput"])
    except subprocess.CalledProcessError as e:
        print(f"Migrations failed: {e}")
        sys.exit(1)

    # 3. Run collectstatic
    print("Running collectstatic...")
    try:
        subprocess.check_call([sys.executable, "manage.py", "collectstatic", "--noinput", "--clear"])
    except subprocess.CalledProcessError as e:
        print(f"collectstatic failed: {e}")
        sys.exit(1)

    print("Build completed successfully!")

if __name__ == "__main__":
    main()
