"""CLI with argparse for the Scholar PDF downloader."""

import argparse
import logging
import sys
from pathlib import Path

from .downloader import run


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download openly available PDFs for a Google Scholar author (resumable, idempotent).",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=Path("downloads/abdalla_rifai_publications_open_pdfs"),
        help="Output directory (default: downloads/abdalla_rifai_publications_open_pdfs)",
    )
    parser.add_argument(
        "--user-id",
        default="tOH4TiwAAAAJ",
        help="Google Scholar user id (default: tOH4TiwAAAAJ)",
    )
    parser.add_argument(
        "--sleep-min",
        type=float,
        default=0.3,
        help="Min sleep between requests in seconds (default: 0.3)",
    )
    parser.add_argument(
        "--sleep-max",
        type=float,
        default=1.0,
        help="Max sleep between requests in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=45,
        help="Request timeout in seconds (default: 45)",
    )
    parser.add_argument(
        "--max-pubs",
        type=int,
        default=None,
        help="Limit number of publications (for debugging)",
    )
    parser.add_argument(
        "--resume",
        type=lambda x: x.lower() in ("1", "true", "yes"),
        default=True,
        metavar="BOOL",
        help="Resume from manifest; skip already-downloaded (default: true)",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Disable resume; start fresh (overwrites manifest)",
    )
    parser.add_argument(
        "--zip",
        type=lambda x: x.lower() in ("1", "true", "yes"),
        default=True,
        metavar="BOOL",
        help="Create outdir.zip (default: true)",
    )
    parser.add_argument(
        "--no-zip",
        action="store_true",
        help="Do not create ZIP",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
        help="Logging level (default: INFO)",
    )
    args = parser.parse_args()

    if args.no_resume:
        args.resume = False
    if args.no_zip:
        args.zip = False

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    logger = logging.getLogger(__name__)

    try:
        run(
            args.user_id,
            args.outdir,
            sleep_min=args.sleep_min,
            sleep_max=args.sleep_max,
            timeout=args.timeout,
            max_pubs=args.max_pubs,
            resume=args.resume,
            create_zip=args.zip,
        )
    except KeyboardInterrupt:
        logger.warning("Interrupted")
        sys.exit(130)
    except RuntimeError as e:
        if "CAPTCHA" in str(e) or "rate" in str(e).lower():
            logger.error("%s", e)
            logger.info("Retry later from the same network. Do not attempt to bypass CAPTCHA.")
        else:
            logger.exception("Error: %s", e)
        sys.exit(1)
    except Exception as e:
        logger.exception("Fatal error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
