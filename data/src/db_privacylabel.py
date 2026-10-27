from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import qrcode

#db
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from src.database import DATA_DB
from src.errors import EntryIDNotFoundError, ImageIDNotAssociatedError
from src.config import (
    MONGO_COLLECTION_METADATA,
)


NUTRITION_SVG_TEMPLATE = """
<svg width="450" xmlns="http://www.w3.org/2000/svg">
  <style>
    .title {{
        font-family: Arial, sans-serif;
        font-size: 38px;
        font-weight: 900;
        fill: black;
    }}
    .subtitle {{
        font-family: Arial, sans-serif;
        font-size: 18px;
        font-weight: bold;
        fill: black;
    }}
    .section-title {{
        font-family: Arial, sans-serif;
        font-size: 20px;
        font-weight: 900;
        fill: white;
    }}
    .label {{
        font-family: Arial, sans-serif;
        font-size: 18px;
        font-weight: bold;
        fill: black;
    }}
    .value {{
        font-family: Arial, sans-serif;
        font-size: 18px;
        fill: black;
    }}
    .daily-value {{
        font-family: Arial, sans-serif;
        font-size: 16px;
        fill: black;
    }}
    line {{
        stroke: black;
        stroke-width: 1.5;
    }}
  </style>

  <!-- Outer border -->
  <rect x="0" y="0" width="450" height="{height}" fill="white" stroke="black" stroke-width="4"/>

  <!-- Title -->
  <text x="20" y="40" class="title">{title}</text>
  <line x1="20" y1="50" x2="430" y2="50" stroke="black" stroke-width="4"/>

  <!-- Serving info -->
  <text x="20" y="75" class="subtitle">Serving Size: {serving_size}</text>
  <text x="20" y="100" class="subtitle">Servings Per Container: {servings_per_container}</text>
  <line x1="20" y1="110" x2="430" y2="110" stroke="black" stroke-width="2"/>

  <!-- Calories row -->
  <rect x="0" y="115" width="450" height="45" fill="#ffe066"/>
  <text x="20" y="145" class="label">Calories</text>
  <text x="380" y="145" class="value">{calories}</text>
  <line x1="20" y1="160" x2="430" y2="160" stroke="black" stroke-width="2"/>

  <!-- Nutrients rows -->
  {nutrient_rows}
</svg>
"""

def generate_nutrient_rows(nutrients):
    """Generates SVG rows for nutrients with optional %DV and icons."""
    y = 170
    rows_svg = ""
    for i, n in enumerate(nutrients):
        # Alternating background colors
        bg_color = "#f8f8f8" if i % 2 == 0 else "#ffffff"

        icon_svg = f'<text x="10" y="{y+20}" font-size="16">{n.get("icon","")}</text>' if n.get("icon") else ""

        rows_svg += f"""
        <rect x="0" y="{y-10}" width="450" height="40" fill="{bg_color}"/>
        {icon_svg}
        <text x="40" y="{y+20}" class="label">{n['name']}</text>
        <text x="380" y="{y+20}" class="value">{n['amount']}</text>
        <text x="430" y="{y+20}" class="daily-value">{n.get('dv','')}</text>
        <line x1="20" y1="{y+30}" x2="430" y2="{y+30}"/>
        """
        y += 40
    return rows_svg, y + 10

'''
async def generate_privacy_label(entry_id):
    
    metadata_collection = DATA_DB.get_collection(MONGO_COLLECTION_METADATA)

    entry_data = await metadata_collection.find_one({"_id": entry_id})

    if not entry_data:
        return None, None
    print(entry_data)

    
    title: str = "Privacy Label"
    calories: int = 0
    fat: int = 0
    carbs: int = 0
    protein: int = 0
    
    nutrients = [
        ("Hersteller", entry_data['manufacturer']),
        ("Modell", entry_data['manufacturer']),
    
    ]

    title: str = "Nutrition Facts"
    serving_size: str = "1 package (50g)"
    servings_per_container: str = "2"
    calories: int = 200
    total_fat: str = "10g"
    saturated_fat: str = "3g"
    sodium: str = "150mg"
    total_carbs: str = "30g"
    fiber: str = "5g"
    sugars: str = "12g"
    protein: str = "8g"

    nutrients = [
        {"name":"Total Fat","amount":total_fat,"dv":"15%","icon":"🥑"},
        {"name":"Saturated Fat","amount":saturated_fat,"dv":"15%","icon":"🧈"},
        {"name":"Sodium","amount":sodium,"dv":"6%","icon":"🧂"},
        {"name":"Total Carbohydrates","amount":total_carbs,"dv":"11%","icon":"🍞"},
        {"name":"Dietary Fiber","amount":fiber,"dv":"20%","icon":"🌾"},
        {"name":"Sugars","amount":sugars,"dv":"—","icon":"🍬"},
        {"name":"Protein","amount":protein,"dv":"16%","icon":"🥩"},
    ]

    nutrient_rows_svg, total_height = generate_nutrient_rows(nutrients)

    svg_content = NUTRITION_SVG_TEMPLATE.format(
        title=title,
        calories=calories,
        serving_size=serving_size,
        servings_per_container=servings_per_container,
        nutrient_rows=nutrient_rows_svg,
        height=total_height + 20
    )

    return svg_content, "image/svg+xml"
'''


def add_qr_to_image(base_img: Image.Image, data: str, x: int, y: int, size: int = 200):
    """Generate QR code and paste it into the base PIL image."""
    
    # Generate QR code
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2
    )
    qr.add_data(data)
    qr.make(fit=True)

    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    # Resize QR to desired size
    qr_img = qr_img.resize((size, size), Image.Resampling.NEAREST)

    # Paste onto base image
    base_img.paste(qr_img, (x, y))

    return base_img
    
async def generate_privacy_label(entry_id):
    
    metadata_collection = DATA_DB.get_collection(MONGO_COLLECTION_METADATA)

    entry_data = await metadata_collection.find_one({"_id": entry_id})

    if not entry_data:
        return None, None
        
    company_name = entry_data['manufacturer']

    font_dir = '/workdir/data/fonts'
    
    font_path_regular = f"{font_dir}/HelveticaNeueMedium.otf"
    font_path_bold = f"{font_dir}/HelveticaNeueBold.otf"
    
      # Load fonts
    font_h1 = ImageFont.truetype(font_path_bold, 42)
    font_h2 = ImageFont.truetype(font_path_regular, 28)
    font_hdr = ImageFont.truetype(font_path_bold, 26)
    font_reg = ImageFont.truetype(font_path_regular, 22)
    font_small = ImageFont.truetype(font_path_regular, 20)
    
    font_bold = ImageFont.truetype(font_path_bold, 22)

    width = 1000
    y = 20

    img = Image.new("RGB", (width, 1400), "white")
    draw = ImageDraw.Draw(img)
    
    def text_centered(text, font, color, x, y = -1):
        nonlocal draw
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]

        x = (img.width - w) // 2
        
        if y == -1:
            y = (img.height - h) // 2
        
        draw.text((x, y), text, font=font, fill=color)
    
    
    

    def line(thickness=2, pad=10):
        nonlocal y
        draw.line((pad, y, width - pad, y), fill="black", width=thickness)
        y += thickness + 10
    

    def shaded_header(text, font):
        nonlocal y
        # light gray box
        
        nonlocal draw
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        
        draw.rectangle((10, y, w + 10*3, y + 50), fill="#E3E3E3")
        draw.text((20, y + 8), text, fill="black", font=font)
        y += 50

    # --- MAIN TITLE ---
    text_centered('Fakten über die Privatheit', font_h1, "black", width // 2, y )
    # draw.text((10, y), "Fakten über die Privatheit", font=font_h1, fill="black")
    y += 60

    # Subtitle
    draw.text((10, y), f"Gerät: {entry_data['manufacturer']} {entry_data['model']}", font=font_h2, fill="black")
    y += 55

    
    headingx = 200
    # WHAT section
    shaded_header("WELCHE", font_hdr)
    draw.text((headingx, y - 40), "Informationen werden erhoben?", font=font_hdr, fill="black")
    line(3)

    # List rows
    rows = [
        ("Standortdaten", "über die App"),
        ("Medizinische Daten", "über einen Herzschlagsensor"),
        ("Name, Vorname, Geburtsdatum, Geschlecht", "Bei der Accounterstellung"),
        ("Kaufdaten", "")
    ]

    for title, sub in rows:
        draw.text((20, y), title, font=font_bold, fill="black")
        y += 28
        if sub:
            draw.text((20, y), sub, font=font_reg, fill="black")
            y += 32
        else:
            y += 20
        line(1)

    #
    
    shaded_header("WOHIN", font_hdr)
    draw.text((headingx, y - 40), "fließen deine Daten?", font=font_hdr, fill="black")
    # draw.text((700, y - 40), "Can you limit this use?", font=font_hdr, fill="black")
    line(3)

    how_rows = [
        ("Deutschland", "Betrieben von Amazon (USA)", "No"),
        ("Frankreich", "Betrieben von OVH SAS (Frankreich)", "Yes"),
        # ("For profiling purposes–", "to do analysis with your data, both linked and not linked to you", "This is only used on your request")
    ]

    for title, desc, rightcol in how_rows:
        draw.text((20, y), title, font=font_bold, fill="black")
        y += 28
        draw.text((20, y), desc, font=font_reg, fill="black")
        # draw.text((700, y - 28), rightcol, font=font_reg, fill="black")
        y += 32
        line(1)

    #
    '''
    shaded_header("WOHIN", font_hdr)
    draw.text((headingx, y - 40), "may your information be shared with?", font=font_hdr, fill="black")
    # draw.text((700, y - 40), "Can you limit this sharing?", font=font_hdr, fill="black")
    line(3)

    draw.text((20, y), "Our company and companies who help us.", font=font_bold, fill="black")
    draw.text((20, y + 30), "Companies who have similar policies to ours", font=font_bold, fill="black")
    # draw.text((700, y), "No", font=font_reg)
    y += 70
    line(3)
    '''

    # CONTACT US section
    shaded_header("WEITERE INFORMATIONEN", font_hdr)
    # draw.text((290, y - 40), "Siehe https://platform.iot-privacy.info/", font=font_reg, fill="black")
    y += 10

    draw.text((20, y), 
              "Siehe https://platform.iot-privacy.info/"+entry_id+"\nWer wir sind: Ein unabhängiges Forschungsprojekt der Universität Gießen\nUnboxing IoT Privacy",
              font=font_small, fill="black")

    # Crop image to actual content height
    height = y + 80
    
    draw.line((1, 1, width - 1*2, 1), fill="black", width=2) # h top
    draw.line((1, 1, 1, height-1*4), fill="black", width=2) # v l
    draw.line((width - 1*3, 1, width - 1*3, height-1*4), fill="black", width=2) # v r
    draw.line((1, height-1*4, width - 1*2, height-1*4), fill="black", width=2) # h top

    
    img = img.crop((0, 0, width, height))
    
      
    # Draw rect

    
    qr_size = 160
    add_qr_to_image(img, "https://platform.iot-privacy.info/device/"+entry_id, width-qr_size-4, y +80-qr_size-4, qr_size)

    # Save to BytesIO
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)


    return buf.getvalue(), "image/png"