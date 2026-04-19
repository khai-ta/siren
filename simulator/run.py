"""CLI entrypoint for the simulator"""

import argparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Siren simulator")
    parser.add_argument("--incident", default="cascading_timeout", help="Incident type name")
    parser.add_argument("--duration", type=int, default=60, help="Duration in minutes")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(f"Simulator scaffold ready. incident={args.incident} duration={args.duration}m")


if __name__ == "__main__":
    main()
