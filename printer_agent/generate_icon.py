"""
printer_agent/generate_icon.py
------------------------------
Generates a multi-resolution Windows .ico file for the Printer Agent Executable.
"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
ICO_PATH = ASSETS_DIR / "printer_agent.ico"


def generate_ico():
    from PIL import Image, ImageDraw

    resolutions = [16, 32, 48, 64, 128, 256]
    images = []

    for dim in resolutions:
        scale = dim / 64.0
        img = Image.new("RGBA", (dim, dim), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # 1. Top Paper Feed Sheet
        p_box = [18 * scale, 4 * scale, 46 * scale, 26 * scale]
        draw.rounded_rectangle(p_box, radius=max(1, int(2 * scale)), fill=(248, 250, 252, 255), outline=(148, 163, 184, 255), width=max(1, int(2 * scale)))

        # Paper lines
        if dim >= 32:
            draw.line([22 * scale, 11 * scale, 42 * scale, 11 * scale], fill=(203, 213, 225, 255), width=max(1, int(1.5 * scale)))
            draw.line([22 * scale, 16 * scale, 38 * scale, 16 * scale], fill=(203, 213, 225, 255), width=max(1, int(1.5 * scale)))

        # 2. Main Printer Body (Slate Navy)
        b_box = [8 * scale, 20 * scale, 56 * scale, 54 * scale]
        draw.rounded_rectangle(b_box, radius=max(2, int(6 * scale)), fill=(30, 41, 59, 255), outline=(71, 85, 105, 255), width=max(1, int(2 * scale)))

        # Feed slit
        draw.rectangle([16 * scale, 21 * scale, 48 * scale, 24 * scale], fill=(15, 23, 42, 255))

        # Output slit
        draw.rectangle([14 * scale, 38 * scale, 50 * scale, 42 * scale], fill=(15, 23, 42, 255))

        # 3. Printed Paper Output
        o_box = [18 * scale, 40 * scale, 46 * scale, 60 * scale]
        draw.rounded_rectangle(o_box, radius=max(1, int(2 * scale)), fill=(248, 250, 252, 255), outline=(148, 163, 184, 255), width=max(1, int(2 * scale)))

        if dim >= 32:
            draw.line([22 * scale, 46 * scale, 42 * scale, 46 * scale], fill=(100, 116, 139, 255), width=max(1, int(1.5 * scale)))
            draw.line([22 * scale, 51 * scale, 36 * scale, 51 * scale], fill=(100, 116, 139, 255), width=max(1, int(1.5 * scale)))

        # 4. Status Indicator (Bright Blue / Green)
        led_box = [46 * scale, 46 * scale, 60 * scale, 60 * scale]
        draw.ellipse(led_box, fill=(16, 185, 129, 255), outline=(255, 255, 255, 255), width=max(1, int(1.5 * scale)))

        images.append(img)

    # Save multi-size .ico
    images[0].save(
        ICO_PATH,
        format="ICO",
        sizes=[(d, d) for d in resolutions],
        append_images=images[1:],
    )
    print(f"Generated Windows Application Icon: {ICO_PATH}")


if __name__ == "__main__":
    generate_ico()
