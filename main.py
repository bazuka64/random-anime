import json
import random
import re
import threading
import tkinter as tk
import urllib.parse
import urllib.request
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from io import BytesIO
from pathlib import Path
from tkinter import messagebox, ttk

try:
    from PIL import Image, ImageTk
except ImportError:  # Pillow is needed for JPG thumbnails from Jikan.
    Image = None
    ImageTk = None


API_URL = "https://api.jikan.moe/v4/anime"
CONFIG_PATH = Path(__file__).with_name("config.json")
SEARCH_SUFFIX = " free video"
TILE_COLUMNS = 4
TILE_COUNT = 24
TILE_WIDTH = 200
TILE_HEIGHT = 390
REQUEST_TIMEOUT_SECONDS = 15
IMAGE_TIMEOUT_SECONDS = 5
THUMBNAIL_SIZE = (180, 220)


@dataclass(frozen=True)
class Anime:
    title: str
    search_title: str
    year: int | None
    score: float | None
    anime_type: str | None
    thumbnail_url: str | None
    thumbnail_data: bytes | None = None

    @property
    def subtitle(self) -> str:
        parts: list[str] = []
        if self.year:
            parts.append(str(self.year))
        if self.anime_type:
            parts.append(self.anime_type)
        if self.score:
            parts.append(f"★ {self.score}")
        return " / ".join(parts)


def fetch_random_anime(limit: int = TILE_COUNT) -> list[Anime]:
    """Fetch anime from a random Jikan page.

    Jikan does not provide a direct "historical random list" endpoint, so this
    samples a random page from the anime catalogue sorted by popularity. That
    gives a broad mix across eras without requiring an API key.
    """
    page = random.randint(1, 200)
    params = urllib.parse.urlencode(
        {
            "page": page,
            "limit": limit,
            "order_by": "popularity",
            "sort": "asc",
            "sfw": "true",
        }
    )
    request = urllib.request.Request(
        f"{API_URL}?{params}",
        headers={"User-Agent": "random-anime-tkinter/1.0"},
    )

    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode("utf-8"))

    anime_list: list[Anime] = []
    for item in payload.get("data", []):
        search_title = item.get("title_english") or item.get("title")
        title = item.get("title_japanese") or search_title
        if not title or not search_title:
            continue
        anime_list.append(
            Anime(
                title=title,
                search_title=search_title,
                year=item.get("year"),
                score=item.get("score"),
                anime_type=item.get("type"),
                thumbnail_url=get_thumbnail_url(item),
            )
        )

    random.shuffle(anime_list)
    selected = anime_list[:limit]
    return fetch_thumbnails(selected)


def get_thumbnail_url(item: dict) -> str | None:
    images = item.get("images", {})
    jpg_images = images.get("jpg", {})
    return (
        jpg_images.get("large_image_url")
        or jpg_images.get("image_url")
        or jpg_images.get("small_image_url")
    )


def fetch_thumbnails(anime_list: list[Anime]) -> list[Anime]:
    with ThreadPoolExecutor(max_workers=8) as executor:
        return list(executor.map(fetch_thumbnail, anime_list))


def fetch_thumbnail(anime: Anime) -> Anime:
    if not anime.thumbnail_url:
        return anime

    try:
        request = urllib.request.Request(
            anime.thumbnail_url,
            headers={"User-Agent": "random-anime-tkinter/1.0"},
        )
        with urllib.request.urlopen(request, timeout=IMAGE_TIMEOUT_SECONDS) as response:
            return replace(anime, thumbnail_data=response.read())
    except Exception:
        return anime


def create_thumbnail_image(thumbnail_data: bytes | None):
    if not thumbnail_data or Image is None or ImageTk is None:
        return None

    try:
        image = Image.open(BytesIO(thumbnail_data)).convert("RGB")
        resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
        image.thumbnail(THUMBNAIL_SIZE, resampling)

        canvas = Image.new("RGB", THUMBNAIL_SIZE, "#0f172a")
        x = (THUMBNAIL_SIZE[0] - image.width) // 2
        y = (THUMBNAIL_SIZE[1] - image.height) // 2
        canvas.paste(image, (x, y))
        return ImageTk.PhotoImage(canvas)
    except Exception:
        return None


class RandomAnimeApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Random Anime Tiles")
        self.geometry(load_window_geometry())
        self.minsize(720, 520)
        self.configure(bg="#121826")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.status_text = tk.StringVar(
            value="Jikan APIからアニメとサムネ画像を取得中..."
        )
        self.refresh_button: ttk.Button | None = None
        self.tiles_canvas: tk.Canvas | None = None
        self.tiles_frame: tk.Frame | None = None

        self._build_layout()
        self.load_anime()

    def _on_close(self) -> None:
        save_window_geometry(self.geometry())
        self.destroy()

    def _build_layout(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TButton", font=("Yu Gothic UI", 11), padding=(12, 8))

        header = tk.Frame(self, bg="#121826")
        header.pack(fill="x", padx=20, pady=(18, 10))

        title = tk.Label(
            header,
            text="歴代アニメ ランダムタイル",
            font=("Yu Gothic UI", 22, "bold"),
            fg="#f8fafc",
            bg="#121826",
        )
        title.pack(side="left")

        self.refresh_button = ttk.Button(header, text="再取得", command=self.load_anime)
        self.refresh_button.pack(side="right")

        description = tk.Label(
            self,
            text="タイルをクリックすると、ブラウザで「英語タイトル free video」を検索します。",
            font=("Yu Gothic UI", 11),
            fg="#cbd5e1",
            bg="#121826",
            anchor="w",
        )
        description.pack(fill="x", padx=22)

        tiles_container = tk.Frame(self, bg="#121826")
        tiles_container.pack(fill="both", expand=True, padx=18, pady=18)

        self.tiles_canvas = tk.Canvas(
            tiles_container,
            bg="#121826",
            highlightthickness=0,
            borderwidth=0,
        )
        scrollbar = ttk.Scrollbar(
            tiles_container,
            orient="vertical",
            command=self.tiles_canvas.yview,
        )
        self.tiles_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.tiles_canvas.pack(side="left", fill="both", expand=True)

        self.tiles_frame = tk.Frame(self.tiles_canvas, bg="#121826")
        self.tiles_canvas.create_window((0, 0), window=self.tiles_frame, anchor="nw")
        self.tiles_frame.bind(
            "<Configure>",
            lambda _event: self.tiles_canvas.configure(
                scrollregion=self.tiles_canvas.bbox("all")
            ),
        )
        self.bind_all("<MouseWheel>", self._on_mousewheel)
        self.bind_all("<Button-4>", self._on_mousewheel)
        self.bind_all("<Button-5>", self._on_mousewheel)

        status = tk.Label(
            self,
            textvariable=self.status_text,
            font=("Yu Gothic UI", 10),
            fg="#94a3b8",
            bg="#121826",
            anchor="w",
        )
        status.pack(fill="x", padx=22, pady=(0, 14))

    def _on_mousewheel(self, event: tk.Event) -> None:
        if not self.tiles_canvas:
            return

        if getattr(event, "num", None) == 4:
            self.tiles_canvas.yview_scroll(-1, "units")
        elif getattr(event, "num", None) == 5:
            self.tiles_canvas.yview_scroll(1, "units")
        else:
            self.tiles_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def load_anime(self) -> None:
        if self.refresh_button:
            self.refresh_button.configure(state="disabled")
        self.status_text.set("Jikan APIからアニメとサムネ画像を取得中...")
        self._clear_tiles()

        thread = threading.Thread(target=self._load_anime_worker, daemon=True)
        thread.start()

    def _load_anime_worker(self) -> None:
        try:
            anime_list = fetch_random_anime()
        except Exception as exc:  # noqa: BLE001 - show the actual API/network error to the user
            self.after(0, lambda: self._show_error(exc))
            return

        self.after(0, lambda: self._render_tiles(anime_list))

    def _show_error(self, exc: Exception) -> None:
        if self.refresh_button:
            self.refresh_button.configure(state="normal")
        self.status_text.set("取得に失敗しました。時間を置いて再取得してください。")
        messagebox.showerror(
            "取得エラー", f"Jikan APIから取得できませんでした。\n\n{exc}"
        )

    def _clear_tiles(self) -> None:
        if not self.tiles_frame:
            return
        for child in self.tiles_frame.winfo_children():
            child.destroy()

    def _render_tiles(self, anime_list: list[Anime]) -> None:
        if self.refresh_button:
            self.refresh_button.configure(state="normal")

        if not anime_list:
            self.status_text.set("アニメが見つかりませんでした。再取得してください。")
            return

        for index, anime in enumerate(anime_list):
            row = index // TILE_COLUMNS
            column = index % TILE_COLUMNS
            tile = self._create_tile(anime)
            tile.grid(row=row, column=column, padx=8, pady=8)

        if self.tiles_frame:
            for column in range(TILE_COLUMNS):
                self.tiles_frame.grid_columnconfigure(column, minsize=TILE_WIDTH + 16)

        if self.tiles_canvas:
            self.tiles_canvas.yview_moveto(0)

        if Image is None or ImageTk is None:
            self.status_text.set(
                f"{len(anime_list)}件表示中。サムネ表示には Pillow をインストールしてください。"
            )
        else:
            image_count = sum(1 for anime in anime_list if anime.thumbnail_data)
            self.status_text.set(
                f"{len(anime_list)}件表示中 / サムネ{image_count}件。クリックで検索します。"
            )

    def _create_tile(self, anime: Anime) -> tk.Frame:
        tile = tk.Frame(
            self.tiles_frame,
            width=TILE_WIDTH,
            height=TILE_HEIGHT,
            bg="#1e293b",
            highlightbackground="#334155",
            highlightthickness=1,
            cursor="hand2",
        )
        tile.grid_propagate(False)
        tile.pack_propagate(False)
        tile.bind("<Button-1>", lambda _event: open_search(anime.search_title))

        thumbnail = create_thumbnail_image(anime.thumbnail_data)
        if thumbnail:
            image_label = tk.Label(tile, image=thumbnail, bg="#0f172a", cursor="hand2")
            image_label.image = thumbnail
        else:
            image_label = tk.Label(
                tile,
                text="No Image",
                font=("Yu Gothic UI", 11, "bold"),
                fg="#64748b",
                bg="#0f172a",
                width=18,
                height=10,
                cursor="hand2",
            )
        image_label.pack(fill="x", padx=10, pady=(10, 8))
        image_label.bind("<Button-1>", lambda _event: open_search(anime.search_title))

        title = tk.Label(
            tile,
            text=anime.title,
            font=("Yu Gothic UI", 11, "bold"),
            fg="#f8fafc",
            bg="#1e293b",
            wraplength=176,
            justify="center",
            cursor="hand2",
        )
        title.pack(expand=True, fill="both", padx=12, pady=(0, 8))
        title.bind("<Button-1>", lambda _event: open_search(anime.search_title))

        subtitle_text = anime.subtitle or "詳細不明"
        subtitle = tk.Label(
            tile,
            text=subtitle_text,
            font=("Yu Gothic UI", 10),
            fg="#93c5fd",
            bg="#1e293b",
            cursor="hand2",
        )
        subtitle.pack(fill="x", padx=12, pady=(0, 14))
        subtitle.bind("<Button-1>", lambda _event: open_search(anime.search_title))

        return tile


def load_window_geometry() -> str:
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as file:
            config = json.load(file)
        width = int(config.get("window_width", 920))
        height = int(config.get("window_height", 700))
        x = config.get("window_x")
        y = config.get("window_y")
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        width = 920
        height = 700
        x = None
        y = None

    geometry = f"{max(width, 720)}x{max(height, 520)}"
    if x is not None and y is not None:
        geometry += f"{int(x):+d}{int(y):+d}"
    return geometry


def save_window_geometry(geometry: str) -> None:
    match = re.match(r"^(\d+)x(\d+)([+-]\d+)([+-]\d+)", geometry)
    if not match:
        return

    width_text, height_text, x_text, y_text = match.groups()
    config = {
        "window_width": max(int(width_text), 720),
        "window_height": max(int(height_text), 520),
        "window_x": int(x_text),
        "window_y": int(y_text),
    }

    try:
        with CONFIG_PATH.open("w", encoding="utf-8") as file:
            json.dump(config, file, ensure_ascii=False, indent=2)
    except OSError:
        pass


def open_search(title: str) -> None:
    query = urllib.parse.quote_plus(f"{title}{SEARCH_SUFFIX}")
    webbrowser.open_new_tab(f"https://www.google.com/search?q={query}")


if __name__ == "__main__":
    app = RandomAnimeApp()
    app.mainloop()
