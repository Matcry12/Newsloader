"""One command for the pipeline."""

import argparse


def main() -> None:
    """Run a pipeline subcommand."""
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    digest_parser = commands.add_parser("digest")
    digest_parser.add_argument("--limit", type=int)
    digest_parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from newsloader import digest

    if args.command == "digest":
        digest.main(args.limit, args.dry_run)


if __name__ == "__main__":
    main()
