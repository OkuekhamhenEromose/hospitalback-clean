#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
    
    # Check if we're running a management command that should skip early_init
    skip_early_init = len(sys.argv) > 1 and sys.argv[1] in ['makemigrations', 'migrate', 'collectstatic']
    
    if not skip_early_init:
        try:
            # Only import early_init for server commands
            import api.early_init
            print("[MANAGE.PY] Loaded early_init")
        except ImportError as e:
            print(f"[MANAGE.PY] Warning: Could not load early_init: {e}")
        except Exception as e:
            print(f"[MANAGE.PY] Warning: Error in early_init: {e}")
    else:
        print(f"[MANAGE.PY] Skipping early_init for command: {sys.argv[1]}")
    
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()