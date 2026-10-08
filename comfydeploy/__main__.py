import argparse
import json
import platform
import shutil


def main():
    parser = argparse.ArgumentParser(description="ComfyDeploy")
    parser.add_argument("command", choices=["discover", "plan"])
    args = parser.parse_args()
    if args.command == "discover":
        print(json.dumps({"platform": platform.platform(), "docker": bool(shutil.which("docker")), "nvidia_smi": bool(shutil.which("nvidia-smi"))}, indent=2))
    else:
        print("Deployment planning is not implemented in this bootstrap.")


if __name__ == "__main__":
    main()
