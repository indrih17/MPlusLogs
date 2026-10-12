"""Build reproducible Windows icons from the M+ vector mark. Requires Pillow."""
from pathlib import Path
from PIL import Image, ImageDraw

DIRECTORY = Path(__file__).with_name("assets")


def build():
    DIRECTORY.mkdir(exist_ok=True)
    scale = 8
    image = Image.new("RGBA", (64 * scale, 64 * scale))
    draw = ImageDraw.Draw(image)
    def points(values):
        return [(x * scale, y * scale) for x, y in values]
    draw.rounded_rectangle((0, 0, 64 * scale - 1, 64 * scale - 1), radius=14 * scale, fill="#7c3aed")
    draw.polygon(points([(9,46),(9,20),(17,20),(25,32),(33,20),(41,20),(41,46),(33,46),(33,33),(25,44),(17,33),(17,46)]), fill="#ffffff")
    draw.polygon(points([(47,14),(53,14),(53,21),(60,21),(60,27),(53,27),(53,34),(47,34),(47,27),(40,27),(40,21),(47,21)]), fill="#e9d5ff")
    image.resize((256,256),Image.Resampling.LANCZOS).save(DIRECTORY / "mpluslogs.png")
    image.save(DIRECTORY / "curseforge-logo.png")
    image.resize((256,256),Image.Resampling.LANCZOS).save(DIRECTORY / "mpluslogs.ico", sizes=[(16,16),(20,20),(24,24),(32,32),(40,40),(48,48),(64,64),(128,128),(256,256)])
    (DIRECTORY / "mpluslogs.svg").write_text('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="14" fill="#7c3aed"/>
<path d="M9 46V20h8l8 12 8-12h8v26h-8V33l-8 11-8-11v13Z" fill="white"/>
<path d="M47 14h6v7h7v6h-7v7h-6v-7h-7v-6h7Z" fill="#e9d5ff"/>
</svg>''', encoding="utf-8")


if __name__ == "__main__":
    build()
