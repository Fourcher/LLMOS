import sys

if len(sys.argv) > 1 and sys.argv[1] == "daemon":
    from .daemon import main
else:
    from .client import main
main()
