"""Generate schematic WCL setup examples, with no account data or credentials."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from personal_api import CLIENT_NAME, EXAMPLE_ID
from wcl_oauth import REDIRECT_URI


def build():
    regular = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 18)
    bold = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 20)
    mono = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 17)
    output = Path(__file__).with_name("assets")
    for name, rows in (
        ("form", [("1", "Name", CLIENT_NAME), ("2", "Redirect URIs", REDIRECT_URI), ("3", "Public Client", "[x] Enabled")]),
        ("id", [("1", "Client ID", EXAMPLE_ID), ("2", "Client Secret", "Not needed for a public client")]),
    ):
        image = Image.new("RGB", (680, 236 if name == "form" else 182), "#eef3f9")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((1, 1, 678, image.height - 2), radius=12, fill="#ffffff", outline="#b4c3d6", width=2)
        draw.text((20, 12), "WCL / " + ("Create Client" if name == "form" else "Your public client"), font=bold, fill="#19365b")
        draw.text((532, 16), "EXAMPLE", font=regular, fill="#63748b")
        for index, (number, label, value) in enumerate(rows):
            y = 52 + index * 57
            draw.ellipse((20, y + 8, 46, y + 34), fill="#2563ad")
            draw.text((28, y + 8), number, font=regular, fill="white")
            draw.text((58, y), label, font=regular, fill="#44546a")
            draw.text((202, y + 13), value, font=mono, fill="#17283e")
        image.save(output / ("personal-api-" + name + ".png"))


if __name__ == "__main__":
    build()
