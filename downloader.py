import random
import time
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import cast
from urllib.parse import urlparse

import httpx
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError
from rich import get_console
from rich.live import Live
from rich.console import Group
from rich.table import Column
from rich.progress import (
    BarColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
    MofNCompleteColumn,
    TaskID,
    TotalFileSizeColumn,
    ProgressColumn,
)

from .episode_extra_info import EpisodeWithExtraInfo
from .error_handeling import YDL_log_filter, reaction_to
from ..langs import Lang
from .config import PlayersConfig, config


logger = logging.getLogger(__name__)
logger.addFilter(YDL_log_filter)

console = get_console()
download_progress_list: list[str | ProgressColumn] = [
    "[bold blue]{task.fields[episode_name]}",
    BarColumn(bar_width=None),
    "[progress.percentage]{task.percentage:>3.1f}%",  # TODO: should disappear if the console is not wide enough
    TransferSpeedColumn(),
    TotalFileSizeColumn(),
    TimeRemainingColumn(compact=True, elapsed_when_finished=True),
]
if config.show_players:
    download_progress_list.insert(
        1,
        TextColumn(
            "[green]{task.fields[site]}",
            table_column=Column(max_width=12),
            justify="right",
        ),
    )

download_progress = Progress(*download_progress_list, console=console)

total_progress = Progress(
    TextColumn("[bold cyan]{task.description}"),
    BarColumn(bar_width=None),
    MofNCompleteColumn(),
    TimeRemainingColumn(elapsed_when_finished=True),
    console=console,
)
progress = Group(total_progress, download_progress)


def download(
    episode: EpisodeWithExtraInfo,
    path: Path,
    episode_path: str = "{episode}",
    prefer_languages: list[Lang] = ["VOSTFR"],
    players_config: PlayersConfig = PlayersConfig([], []),
    concurrent_fragment_downloads: int = 3,
    max_retry_time: int = 1024,
    format: str = "",
    format_sort: str = "",
) -> None:
    if not any(episode.warpped.languages.values()):
        logger.error("No player available")
        return

    me = download_progress.add_task(
        "download", episode_name=episode.warpped.name, site="", total=None
    )
    task = download_progress.tasks[me]

    full_path = (
        path
        / episode_path.format(
            serie=episode.warpped.serie_name,
            season=episode.warpped.season_name,
            episode=episode.warpped.name,
            release_year_parentheses=episode.release_year_parentheses(),
        )
    ).expanduser()

    def hook(data: dict) -> None:
        if data.get("status") != "downloading":
            return

        # Directly accessing .total is needed to not reset the speed
        task.total = data.get("total_bytes") or data.get("total_bytes_estimate")
        download_progress.update(me, completed=data.get("downloaded_bytes", 0))

    option = {
        "outtmpl": f"{full_path}.%(ext)s",
        "concurrent_fragment_downloads": concurrent_fragment_downloads,
        "progress_hooks": [hook],
        "logger": logger,
        "format": format,
        "format_sort": format_sort.split(","),
    }

    for player in episode.warpped.consume_player(
        prefer_languages, players_config.prefers, players_config.bans
    ):
        retry_time = 1
        sucess = False
        download_progress.update(me, site=urlparse(player).hostname)

        while True:
            # Check if the video is not accessible through vidmoly
            try:
                if (
                    player.startswith("https://vidmoly.")
                    and "Please wait"  # Note "Please wait" appear in all the player page
                    not in httpx.get(player, headers={"User-Agent": ""}).text
                ):
                    break
            except httpx.ConnectError:
                break

            try:
                with YoutubeDL(option) as ydl:  # type: ignore
                    error_code = cast(int, ydl.download([player]))

                    if not error_code:
                        sucess = True
                    else:
                        logger.fatal(
                            f"The download encountered an error code {error_code}. Please report this to the developer with URL: {player}",
                        )

                    break

            except DownloadError as exception:
                # yt-dlp thinks vidmoly is unsupported but it just need wait
                if (
                    player.startswith("https://vidmoly.")
                    and exception.msg is not None
                    and "Unsupported URL: https://vidmoly.net/" in exception.msg
                ):
                    exception.msg = "Waiting for vidmoly"

                match reaction_to(exception.msg):
                    case "continue":
                        break

                    case "retry":
                        if retry_time >= max_retry_time:
                            break

                        logger.warning(
                            f"{episode.warpped.name} interrupted. Retrying in {retry_time}s."
                        )
                        # random is used to spread the resume time and so mitigate deadlock when multiple downloads resume at the same time
                        time.sleep(retry_time * random.uniform(0.8, 1.2))
                        retry_time *= 2

                    case "crash":
                        raise exception

                    case "":
                        logger.fatal(
                            "The above error wasn't handle. Please report it to the developer with URL: %s",
                            player,
                        )
                        break

        if sucess:
            break

    download_progress.update(me, visible=False)
    if total_progress.tasks:
        total_progress.update(TaskID(0), advance=1)


def multi_download(
    episodes: list[EpisodeWithExtraInfo],
    path: Path,
    episode_path: str = "{episode}",
    concurrent_downloads: dict[str, int] = {},
    prefer_languages: list[Lang] = ["VOSTFR"],
    players_config: PlayersConfig = PlayersConfig([], []),
    max_retry_time: int = 1024,
    format: str = "",
    format_sort: str = "",
) -> None:
    """
    Not sure if you can use this function multiple times
    """
    total_progress.add_task("Downloaded", total=len(episodes))
    with Live(progress, console=console):
        with ThreadPoolExecutor(
            max_workers=concurrent_downloads.get("video", 1)
        ) as executor:
            for episode in episodes:
                executor.submit(
                    download,
                    episode,
                    path,
                    episode_path,
                    prefer_languages,
                    players_config,
                    concurrent_downloads.get("fragment", 1),
                    max_retry_time,
                    format,
                    format_sort,
                )
