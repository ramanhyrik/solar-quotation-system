import os
import traceback
from datetime import datetime, timedelta
from io import BytesIO

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    FrameBreak,
    Image,
    NextPageTemplate,
    PageBreak,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.doctemplate import BaseDocTemplate, PageTemplate
from reportlab.platypus.frames import Frame

from chart_generator import generate_monthly_production_chart
from quote_defaults import QUOTE_ACCENT, QUOTE_BACKGROUND, QUOTE_MUTED, QUOTE_SURFACE, QUOTE_TEXT


try:
    import arabic_reshaper
    from bidi.algorithm import get_display

    RTL_AVAILABLE = True
except ImportError:
    RTL_AVAILABLE = False

    def get_display(text):
        return text


def reshape_hebrew(text):
    if text is None:
        return ""

    text_str = str(text)
    if text_str in {"", "None"}:
        return ""

    try:
        if isinstance(text_str, bytes):
            text_str = text_str.decode("utf-8")
        text_str = text_str.encode("utf-8", errors="ignore").decode("utf-8")
    except Exception:
        return str(text)

    if not RTL_AVAILABLE:
        return text_str

    try:
        return get_display(arabic_reshaper.reshape(text_str))
    except Exception:
        return text_str


def escape_for_paragraph(text):
    if text is None:
        return ""

    text_str = str(text)
    try:
        if isinstance(text_str, bytes):
            text_str = text_str.decode("utf-8", errors="replace")
        text_str = text_str.encode("utf-8", errors="replace").decode("utf-8")
    except Exception:
        return ""

    text_str = text_str.replace("&", "&amp;")
    text_str = text_str.replace("<", "&lt;")
    text_str = text_str.replace(">", "&gt;")
    return text_str


def rtl(text):
    return escape_for_paragraph(reshape_hebrew(text))


def trim_signature_whitespace(image_path):
    try:
        img = PILImage.open(image_path)
        if img.mode != "RGBA":
            img = img.convert("RGBA")

        background = PILImage.new("RGBA", img.size, (255, 255, 255, 255))
        composite = PILImage.alpha_composite(background, img)
        gray = composite.convert("L")
        bbox_img = gray.point(lambda x: 0 if x > 250 else 255)
        bbox = bbox_img.getbbox()

        if bbox:
            padding = 2
            bbox = (
                max(0, bbox[0] - padding),
                max(0, bbox[1] - padding),
                min(img.width, bbox[2] + padding),
                min(img.height, bbox[3] + padding),
            )
            img = img.crop(bbox)

        trimmed_path = image_path.replace(".png", "_trimmed.png")
        img.save(trimmed_path, "PNG")
        return trimmed_path
    except Exception:
        return image_path


def create_white_signature_variant(image_path):
    try:
        img = PILImage.open(image_path)
        if img.mode != "RGBA":
            img = img.convert("RGBA")

        alpha = img.getchannel("A")
        white_signature = PILImage.new("RGBA", img.size, (255, 255, 255, 0))
        white_signature.putalpha(alpha)

        variant_path = image_path.replace(".png", "_white.png")
        white_signature.save(variant_path, "PNG")
        return variant_path
    except Exception:
        return image_path


def register_hebrew_font():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    bundled_font_dir = os.path.join(script_dir, "fonts")

    font_paths = [
        (
            os.path.join(bundled_font_dir, "Heebo-Regular.ttf"),
            os.path.join(bundled_font_dir, "Heebo-Bold.ttf"),
        ),
        (
            os.path.join(bundled_font_dir, "Rubik-Regular.ttf"),
            os.path.join(bundled_font_dir, "Rubik-Bold.ttf"),
        ),
        ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
        ("C:/Windows/Fonts/ARIAL.TTF", "C:/Windows/Fonts/ARIALBD.TTF"),
        ("C:/Windows/Fonts/tahoma.ttf", "C:/Windows/Fonts/tahomabd.ttf"),
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ),
    ]

    for regular_path, bold_path in font_paths:
        if not os.path.exists(regular_path):
            continue

        try:
            pdfmetrics.registerFont(TTFont("Hebrew", regular_path))
            if os.path.exists(bold_path):
                pdfmetrics.registerFont(TTFont("Hebrew-Bold", bold_path))
            else:
                pdfmetrics.registerFont(TTFont("Hebrew-Bold", regular_path))
            return True
        except Exception:
            continue

    return False


HEBREW_FONT_AVAILABLE = register_hebrew_font()
FONT_NAME = "Hebrew" if HEBREW_FONT_AVAILABLE else "Helvetica"
FONT_NAME_BOLD = "Hebrew-Bold" if HEBREW_FONT_AVAILABLE else "Helvetica-Bold"

THEME_BACKGROUND = colors.HexColor(QUOTE_BACKGROUND)
THEME_SURFACE = colors.HexColor(QUOTE_SURFACE)
THEME_ACCENT = colors.HexColor(QUOTE_ACCENT)
THEME_MUTED = colors.HexColor(QUOTE_MUTED)
THEME_TEXT = colors.HexColor(QUOTE_TEXT)
THEME_DARK_TEXT = colors.HexColor(QUOTE_BACKGROUND)
FOOTER_HEIGHT = 1.2 * inch


def safe_get(data, key, default=""):
    value = data.get(key)
    if value is None or value == "" or str(value) == "None":
        return default
    return value


def format_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)

    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.2f}".rstrip("0").rstrip(".")


def format_currency(value):
    return f"₪{format_number(value)}"


def format_signed_currency(value):
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return format_currency(value)
    prefix = "-" if numeric < 0 else ""
    return f"{prefix}{format_currency(abs(numeric))}"


def format_multiline_text(text):
    lines = str(text or "").splitlines() or [""]
    output = []
    for line in lines:
        output.append(rtl(line) if line.strip() else "&nbsp;")
    return "<br/>".join(output)


def append_text_section(elements, title, text, heading_style, body_style, spacing=0.08 * inch):
    elements.append(Paragraph(rtl(title), heading_style))
    elements.append(Spacer(1, 0.04 * inch))
    elements.append(Paragraph(format_multiline_text(text), body_style))
    elements.append(Spacer(1, spacing))


def add_page_background(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(THEME_BACKGROUND)
    canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    canvas.restoreState()


def add_page_background_with_footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(THEME_BACKGROUND)
    canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    canvas.setFillColor(THEME_SURFACE)
    canvas.rect(0, 0, A4[0], FOOTER_HEIGHT, fill=1, stroke=0)
    canvas.restoreState()


def build_document(buffer):
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )

    regular_frame = Frame(
        doc.leftMargin,
        doc.bottomMargin,
        doc.width,
        doc.height,
        id="regular",
    )
    last_content_frame = Frame(
        doc.leftMargin,
        1.35 * inch,
        doc.width,
        doc.height - 0.85 * inch,
        id="last_content",
    )
    last_footer_frame = Frame(
        doc.leftMargin,
        0.22 * inch,
        doc.width,
        0.92 * inch,
        id="last_footer",
        showBoundary=0,
    )

    doc.addPageTemplates(
        [
            PageTemplate(id="regular_page", frames=regular_frame, onPage=add_page_background),
            PageTemplate(
                id="last_page",
                frames=[last_content_frame, last_footer_frame],
                onPage=add_page_background_with_footer,
            ),
        ]
    )
    return doc


def build_styles():
    styles = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "QuoteTitle",
            parent=styles["Normal"],
            fontSize=24,
            textColor=THEME_ACCENT,
            spaceAfter=6,
            alignment=TA_RIGHT,
            fontName=FONT_NAME_BOLD,
        ),
        "heading": ParagraphStyle(
            "QuoteHeading",
            parent=styles["Heading2"],
            fontSize=11,
            textColor=THEME_ACCENT,
            spaceAfter=4,
            spaceBefore=6,
            fontName=FONT_NAME_BOLD,
            alignment=TA_RIGHT,
        ),
        "body": ParagraphStyle(
            "QuoteBody",
            parent=styles["Normal"],
            fontSize=8.5,
            leading=12,
            spaceAfter=2,
            textColor=THEME_TEXT,
            fontName=FONT_NAME,
            alignment=TA_RIGHT,
        ),
        "note": ParagraphStyle(
            "QuoteNote",
            parent=styles["Normal"],
            fontSize=7.5,
            leading=10,
            textColor=THEME_MUTED,
            fontName=FONT_NAME,
            alignment=TA_RIGHT,
        ),
        "footer_right": ParagraphStyle(
            "FooterRight",
            parent=styles["Normal"],
            fontSize=8,
            leading=10,
            textColor=THEME_TEXT,
            fontName=FONT_NAME,
            alignment=TA_RIGHT,
        ),
        "footer_left": ParagraphStyle(
            "FooterLeft",
            parent=styles["Normal"],
            fontSize=8,
            leading=10,
            textColor=THEME_TEXT,
            fontName=FONT_NAME,
            alignment=TA_LEFT,
        ),
    }


def build_info_table(rows, col_widths, boxed=False):
    table = Table(rows, colWidths=col_widths)
    style = [
        ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (-1, -1), THEME_TEXT),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]
    if boxed:
        style.extend(
            [
                ("BACKGROUND", (0, 0), (-1, -1), THEME_SURFACE),
                ("GRID", (0, 0), (-1, -1), 0.5, THEME_MUTED),
            ]
        )
    table.setStyle(TableStyle(style))
    return table


def apply_standard_table_style(table):
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), THEME_ACCENT),
                ("TEXTCOLOR", (0, 0), (-1, 0), THEME_DARK_TEXT),
                ("TEXTCOLOR", (0, 1), (-1, -1), THEME_TEXT),
                ("BACKGROUND", (0, 1), (-1, -1), THEME_SURFACE),
                ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                ("FONTNAME", (0, 0), (-1, 0), FONT_NAME_BOLD),
                ("FONTNAME", (0, 1), (-1, -1), FONT_NAME),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("FONTSIZE", (0, 1), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, THEME_MUTED),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )


def apply_cashflow_table_style(table):
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), THEME_ACCENT),
                ("TEXTCOLOR", (0, 0), (-1, 0), THEME_DARK_TEXT),
                ("BACKGROUND", (0, 1), (-1, -2), THEME_SURFACE),
                ("TEXTCOLOR", (0, 1), (-1, -2), THEME_TEXT),
                ("BACKGROUND", (0, -1), (-1, -1), THEME_ACCENT),
                ("TEXTCOLOR", (0, -1), (-1, -1), THEME_DARK_TEXT),
                ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                ("FONTNAME", (0, 0), (-1, 0), FONT_NAME_BOLD),
                ("FONTNAME", (0, 1), (-1, -1), FONT_NAME),
                ("FONTSIZE", (0, 0), (-1, 0), 8.5),
                ("FONTSIZE", (0, 1), (-1, -1), 6.8),
                ("GRID", (0, 0), (-1, -1), 0.5, THEME_MUTED),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )


def get_assumption_values(quote_data):
    return (
        float(quote_data.get("degradation_rate") or 0.004),
        float(quote_data.get("operating_cost_base") or 0.005),
        float(quote_data.get("operating_cost_increase") or 0.02),
        float(quote_data.get("leasing_payment_ratio") or 0.25),
    )


def calculate_purchase_cashflow_total(quote_data):
    total_price = float(quote_data.get("total_price") or 0)
    annual_revenue = float(quote_data.get("annual_revenue") or 0)
    degradation_rate, operating_cost_base, operating_cost_increase, _ = get_assumption_values(
        quote_data
    )
    base_operating_cost = total_price * operating_cost_base
    total_cashflow = -total_price

    for year in range(25):
        production_factor = max(0.0, 1 - (degradation_rate * year))
        yearly_revenue = annual_revenue * production_factor
        yearly_operating_cost = base_operating_cost * ((1 + operating_cost_increase) ** year)
        total_cashflow += yearly_revenue - yearly_operating_cost

    return int(round(total_cashflow))


def calculate_leasing_cashflow_total(quote_data):
    annual_revenue = float(quote_data.get("annual_revenue") or 0)
    degradation_rate, _, _, leasing_ratio = get_assumption_values(quote_data)
    total_cashflow = 0.0

    for year in range(25):
        production_factor = max(0.0, 1 - (degradation_rate * year))
        total_cashflow += annual_revenue * production_factor * leasing_ratio

    return int(round(total_cashflow))


def build_specs_rows(quote_data, not_specified, model_type="purchase"):
    system_size = quote_data.get("system_size", 0) or 0
    roof_area = quote_data.get("roof_area")
    annual_prod = quote_data.get("annual_production", 0) or 0
    rows = [
        [f"{reshape_hebrew('קוט״ש')} {format_number(system_size)}", reshape_hebrew("גודל מערכת:")],
        [f"{reshape_hebrew('מ״ר')} {format_number(roof_area)}" if roof_area else not_specified, reshape_hebrew("שטח גג:")],
        [
            f"{reshape_hebrew('קוט״ש/שנה')} {format_number(annual_prod)}" if annual_prod else not_specified,
            reshape_hebrew("ייצור שנתי:"),
        ],
        [reshape_hebrew(safe_get(quote_data, "maintenance")) or not_specified, reshape_hebrew("תחזוקה:")],
    ]
    if model_type != "leasing":
        rows.append(
            [reshape_hebrew(safe_get(quote_data, "service")) or not_specified, reshape_hebrew("שירות:")]
        )
    return rows


def build_purchase_financial_rows(quote_data):
    total_price = quote_data.get("total_price", 0) or 0
    annual_revenue = quote_data.get("annual_revenue", 0) or 0
    system_value = quote_data.get("system_value_after_25_years")
    total_cashflow = calculate_purchase_cashflow_total(quote_data)
    return [
        [reshape_hebrew("סכום"), reshape_hebrew("תיאור")],
        [format_currency(total_price), reshape_hebrew("סך ההשקעה")],
        [format_currency(annual_revenue), reshape_hebrew("הכנסה שנתית משוערת")],
        [
            format_currency(system_value) if system_value is not None else reshape_hebrew("לא צוין"),
            reshape_hebrew("שווי מערכת לאחר 25 שנה"),
        ],
        [format_currency(total_cashflow), reshape_hebrew("תזרים מצטבר ל-25 שנה")],
    ]


def build_leasing_financial_rows(quote_data):
    total_price = quote_data.get("total_price", 0) or 0
    annual_revenue = quote_data.get("annual_revenue", 0) or 0
    _, _, _, leasing_ratio = get_assumption_values(quote_data)
    annual_customer_income = int(round(annual_revenue * leasing_ratio))
    system_value = quote_data.get("system_value_after_25_years")
    total_cashflow = calculate_leasing_cashflow_total(quote_data)
    return [
        [reshape_hebrew("סכום"), reshape_hebrew("תיאור")],
        [format_currency(total_price), reshape_hebrew("שווי המערכת")],
        [format_currency(annual_customer_income), reshape_hebrew("הכנסה שנתית ללקוח")],
        [
            format_currency(system_value) if system_value is not None else reshape_hebrew("לא צוין"),
            reshape_hebrew("שווי מערכת לאחר 25 שנה"),
        ],
        [format_currency(total_cashflow), reshape_hebrew("תזרים מצטבר ל-25 שנה")],
    ]


def build_purchase_metrics_rows(quote_data):
    total_price = float(quote_data.get("total_price") or 0)
    system_size = float(quote_data.get("system_size") or 0)
    annual_revenue = float(quote_data.get("annual_revenue") or 0)
    price_per_kwp = total_price / system_size if system_size else 0
    roa = (annual_revenue / total_price) * 100 if total_price else 0
    total_cashflow = calculate_purchase_cashflow_total(quote_data)
    return [
        [reshape_hebrew("ערך"), reshape_hebrew("מדד")],
        [format_currency(total_price), reshape_hebrew("עלות כוללת")],
        [format_currency(price_per_kwp), reshape_hebrew("מחיר לקילו-וואט")],
        [f"{roa:.1f}%", reshape_hebrew("תשואה שנתית (ROA)")],
        [format_currency(total_cashflow), reshape_hebrew("תזרים מצטבר 25 שנה")],
    ]


def build_leasing_metrics_rows(quote_data):
    annual_revenue = float(quote_data.get("annual_revenue") or 0)
    stored_system_value = quote_data.get("system_value_after_25_years")
    _, _, _, leasing_ratio = get_assumption_values(quote_data)

    annual_income = annual_revenue * leasing_ratio
    total_cashflow = calculate_leasing_cashflow_total(quote_data)
    system_value = (
        float(stored_system_value)
        if stored_system_value not in (None, "")
        else float(quote_data.get("total_price") or 0)
    )
    total_revenue = system_value + total_cashflow

    return [
        [reshape_hebrew("ערך"), reshape_hebrew("מדד")],
        [format_currency(annual_income), reshape_hebrew("הכנסה שנתית")],
        [format_currency(total_cashflow), reshape_hebrew("תזרים מצטבר ל-25 שנה")],
        [format_currency(system_value), reshape_hebrew("שווי מערכת לאחר 25 שנה")],
        [format_currency(total_revenue), reshape_hebrew("סך הכנסה")],
    ]


def build_purchase_cashflow_rows(quote_data):
    total_price = float(quote_data.get("total_price") or 0)
    annual_revenue = float(quote_data.get("annual_revenue") or 0)
    degradation_rate, operating_cost_base, operating_cost_increase, _ = get_assumption_values(
        quote_data
    )
    base_operating_cost = total_price * operating_cost_base

    rows = [
        [
            reshape_hebrew("תזרים מצטבר"),
            reshape_hebrew("רווח נקי"),
            reshape_hebrew("הכנסה"),
            reshape_hebrew("השקעה"),
            reshape_hebrew("שנה"),
        ],
        [format_signed_currency(-total_price), "-", "-", format_currency(total_price), "0"],
    ]

    total_revenue = 0
    total_net = 0
    cumulative = -total_price

    for year in range(1, 26):
        production_factor = max(0.0, 1 - (degradation_rate * (year - 1)))
        year_revenue = int(round(annual_revenue * production_factor))
        year_operating_cost = int(
            round(base_operating_cost * ((1 + operating_cost_increase) ** (year - 1)))
        )
        year_net = year_revenue - year_operating_cost
        total_revenue += year_revenue
        total_net += year_net
        cumulative += year_net
        rows.append(
            [
                format_signed_currency(cumulative),
                format_currency(year_net),
                format_currency(year_revenue),
                "-",
                str(year),
            ]
        )

    rows.append(
        [
            format_signed_currency(cumulative),
            format_currency(total_net),
            format_currency(total_revenue),
            format_currency(total_price),
            reshape_hebrew("סה״כ"),
        ]
    )
    return rows


def build_leasing_cashflow_rows(quote_data):
    annual_revenue = float(quote_data.get("annual_revenue") or 0)
    degradation_rate, _, _, leasing_ratio = get_assumption_values(quote_data)

    rows = [
        [
            reshape_hebrew("תזרים מצטבר"),
            reshape_hebrew("לקוח"),
            reshape_hebrew("השקעה"),
            reshape_hebrew("שנה"),
        ],
        ["0", "-", "0", "0"],
    ]

    total_customer_income = 0
    cumulative = 0

    for year in range(1, 26):
        production_factor = max(0.0, 1 - (degradation_rate * (year - 1)))
        year_customer_income = int(round(annual_revenue * production_factor * leasing_ratio))
        total_customer_income += year_customer_income
        cumulative += year_customer_income
        rows.append(
            [
                format_currency(cumulative),
                format_currency(year_customer_income),
                "-",
                str(year),
            ]
        )

    rows.append(
        [
            format_currency(cumulative),
            format_currency(total_customer_income),
            "0",
            reshape_hebrew("סה״כ"),
        ]
    )
    return rows


def find_first_existing_path(paths):
    for path in paths:
        if os.path.exists(path):
            return path
    return None


def resolve_offer_image_path(stored_path):
    if not stored_path:
        return None
    if os.path.exists(stored_path):
        return stored_path

    filename = os.path.basename(stored_path)
    if not filename:
        return None

    render_uploads = "/opt/render/project/src/uploads"
    candidates = [
        os.path.join(render_uploads, "quote_images", filename),
        os.path.join("static", "quote_images", filename),
        os.path.join(render_uploads, filename),
        os.path.join("static", filename),
    ]
    return find_first_existing_path(candidates)


def build_header(elements, quote_data, title_text, title_style):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cwd = os.getcwd()

    logo_path = find_first_existing_path(
        [
            os.path.join(cwd, "static", "images", "לוגו .png"),
            os.path.join(script_dir, "static", "images", "לוגו .png"),
            os.path.join(cwd, "static", "images", "logo2.png"),
            os.path.join(script_dir, "static", "images", "logo2.png"),
            os.path.join(cwd, "logo2.png"),
            os.path.join(script_dir, "logo2.png"),
            os.path.join(cwd, "static", "images", "logo.png"),
            os.path.join(script_dir, "static", "images", "logo.png"),
        ]
    )

    subtitle_text = f"הצעת מחיר מספר {safe_get(quote_data, 'quote_number', 'N/A')}"
    title_para = Paragraph(
        (
            f"<para align=right><b><font color='{QUOTE_ACCENT}'>{rtl(title_text)}</font></b>"
            f"<br/><font size=12 color='{QUOTE_TEXT}'>{rtl(subtitle_text)}</font></para>"
        ),
        title_style,
    )

    if logo_path:
        try:
            logo = Image(logo_path, width=2.2 * inch, height=0.9 * inch, kind="proportional")
            table = Table([[logo, title_para]], colWidths=[2.5 * inch, 4.0 * inch])
            table.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("ALIGN", (0, 0), (0, 0), "LEFT"),
                        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                        ("TOPPADDING", (0, 0), (-1, -1), 15),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 15),
                        ("LEFTPADDING", (0, 0), (-1, -1), 20),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 20),
                    ]
                )
            )
            elements.append(table)
        except Exception:
            elements.append(title_para)
    else:
        elements.append(title_para)

    elements.append(Spacer(1, 0.1 * inch))
    return cwd, script_dir


def build_signature_element(
    label_text,
    image_path,
    style,
    image_width,
    image_height,
    make_white=False,
):
    if image_path and os.path.exists(image_path):
        try:
            should_make_white = make_white or os.path.basename(image_path).lower() == "sign.png"
            source_path = (
                create_white_signature_variant(image_path)
                if should_make_white
                else image_path
            )
            trimmed_path = trim_signature_whitespace(source_path)
            signature_image = Image(
                trimmed_path,
                width=image_width,
                height=image_height,
                kind="proportional",
            )
            label = Paragraph(rtl(label_text), style)
            table = Table([[signature_image, label]], colWidths=[image_width, 0.82 * inch])
            table.setStyle(
                TableStyle(
                    [
                        ("ALIGN", (0, 0), (0, 0), "LEFT"),
                        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ]
                )
            )
            return table
        except Exception:
            pass

    placeholder = Paragraph(rtl(f"{label_text} ______________"), style)
    table = Table([[placeholder]], colWidths=[1.9 * inch])
    table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("VALIGN", (0, 0), (0, 0), "BOTTOM"),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 0),
                ("TOPPADDING", (0, 0), (0, 0), 0),
                ("BOTTOMPADDING", (0, 0), (0, 0), 0),
            ]
        )
    )
    return table


def build_footer_table(
    company_info,
    company_name,
    customer_signature_path,
    footer_right_style,
    footer_left_style,
    cwd,
    script_dir,
):
    company_signature_path = find_first_existing_path(
        [
            os.path.join(cwd, "sign.png"),
            os.path.join(script_dir, "sign.png"),
            os.path.join(cwd, "static", "images", "sign.png"),
            os.path.join(script_dir, "static", "images", "sign.png"),
        ]
    )

    company_lines = [f"<b>{escape_for_paragraph(company_name)}</b>"]
    if company_info:
        if company_info.get("company_phone"):
            company_lines.append(
                f"{escape_for_paragraph(company_info['company_phone'])} :{rtl('טלפון')}"
            )
        if company_info.get("company_email"):
            company_lines.append(
                f"{escape_for_paragraph(company_info['company_email'])} :{rtl('אימייל')}"
            )
        if company_info.get("company_address"):
            company_lines.append(f"{rtl(company_info['company_address'])} :{rtl('כתובת')}")
    company_lines.append("")
    company_lines.append(rtl("זמינים לשירותכם בכל שאלה."))
    right_para = Paragraph("<br/>".join(company_lines), footer_right_style)

    customer_signature = build_signature_element(
        "חתימת הלקוח:",
        customer_signature_path,
        footer_left_style,
        1.1 * inch,
        0.5 * inch,
    )
    company_signature = build_signature_element(
        "חתימת החברה:",
        company_signature_path,
        footer_left_style,
        1.0 * inch,
        0.4 * inch,
    )

    footer_table = Table(
        [[customer_signature, company_signature, right_para]],
        colWidths=[1.9 * inch, 1.85 * inch, 2.25 * inch],
    )
    footer_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (1, 0), "BOTTOM"),
                ("VALIGN", (2, 0), (2, 0), "TOP"),
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ("ALIGN", (2, 0), (2, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("RIGHTPADDING", (2, 0), (2, 0), 0),
            ]
        )
    )
    return footer_table


def generate_quote_pdf_base(quote_data, company_info=None, customer_signature_path=None, model_type="purchase"):
    buffer = BytesIO()
    doc = build_document(buffer)
    styles = build_styles()
    elements = []

    company_name = (
        safe_get(company_info, "company_name", "Solar Energy Solutions")
        if company_info
        else "Solar Energy Solutions"
    )
    title_text = "הצעת מחיר"
    cwd, script_dir = build_header(elements, quote_data, title_text, styles["title"])

    today = datetime.now()
    valid_until = today + timedelta(days=30)
    not_specified = reshape_hebrew("לא צוין")

    quote_info_rows = [
        [str(safe_get(quote_data, "quote_number", "N/A")), reshape_hebrew("מספר הצעה:")],
        [today.strftime("%d/%m/%Y"), reshape_hebrew("תאריך:")],
        [valid_until.strftime("%d/%m/%Y"), reshape_hebrew("בתוקף עד:")],
    ]
    elements.append(build_info_table(quote_info_rows, [4.8 * inch, 1.2 * inch]))
    elements.append(Spacer(1, 0.06 * inch))

    customer_rows = [
        [reshape_hebrew(safe_get(quote_data, "customer_name")) or not_specified, reshape_hebrew("שם:")],
        [safe_get(quote_data, "customer_phone", not_specified), reshape_hebrew("טלפון:")],
        [safe_get(quote_data, "customer_email", not_specified), reshape_hebrew("אימייל:")],
        [reshape_hebrew(safe_get(quote_data, "customer_address")) or not_specified, reshape_hebrew("כתובת:")],
    ]
    elements.append(Paragraph(rtl("פרטי לקוח"), styles["heading"]))
    elements.append(Spacer(1, 0.04 * inch))
    elements.append(build_info_table(customer_rows, [4.8 * inch, 1.2 * inch]))
    elements.append(Spacer(1, 0.06 * inch))

    elements.append(Paragraph(rtl("מפרט מערכת"), styles["heading"]))
    elements.append(Spacer(1, 0.04 * inch))
    elements.append(
        build_info_table(
            build_specs_rows(quote_data, not_specified, "leasing"),
            [3.8 * inch, 2.2 * inch],
            boxed=True,
        )
    )
    elements.append(Spacer(1, 0.06 * inch))

    system_size = float(quote_data.get("system_size") or 0)
    annual_production = float(quote_data.get("annual_production") or 0)
    if system_size and annual_production:
        elements.append(Paragraph(rtl("ייצור אנרגיה חודשי"), styles["heading"]))
        elements.append(Spacer(1, 0.04 * inch))
        try:
            chart_bytes = generate_monthly_production_chart(system_size, annual_production)
            chart_image = Image(BytesIO(chart_bytes), width=6.3 * inch, height=2.6 * inch)
            elements.append(chart_image)
            elements.append(Spacer(1, 0.06 * inch))
        except Exception:
            traceback.print_exc()

    elements.append(Paragraph(rtl("מדדים פיננסיים"), styles["heading"]))
    elements.append(Spacer(1, 0.04 * inch))
    metrics_rows = build_leasing_metrics_rows(quote_data)
    metrics_table = Table(metrics_rows, colWidths=[2.1 * inch, 3.9 * inch])
    apply_standard_table_style(metrics_table)
    elements.append(metrics_table)
    elements.append(Spacer(1, 0.06 * inch))

    append_text_section(
        elements,
        "השפעה סביבתית",
        quote_data.get("environmental_impact_text", ""),
        styles["heading"],
        styles["body"],
        spacing=0.06 * inch,
    )

    offer_image_fs_path = resolve_offer_image_path(quote_data.get("offer_image_path"))
    if offer_image_fs_path:
        try:
            offer_image = Image(
                offer_image_fs_path,
                width=6.3 * inch,
                height=4.0 * inch,
                kind="proportional",
            )
            elements.append(Spacer(1, 0.08 * inch))
            elements.append(offer_image)
            elements.append(Spacer(1, 0.06 * inch))
        except Exception:
            traceback.print_exc()

    elements.append(NextPageTemplate("last_page"))
    elements.append(PageBreak())

    elements.append(Paragraph(rtl("ניתוח תזרים מזומנים - 25 שנה"), styles["heading"]))
    elements.append(Spacer(1, 0.04 * inch))
    cashflow_rows = build_leasing_cashflow_rows(quote_data)
    cashflow_widths = [1.7 * inch, 1.7 * inch, 1.7 * inch, 1.1 * inch]
    cashflow_table = Table(cashflow_rows, colWidths=cashflow_widths)
    apply_cashflow_table_style(cashflow_table)
    elements.append(cashflow_table)
    elements.append(Spacer(1, 0.06 * inch))

    append_text_section(
        elements,
        "הנחות יסוד",
        quote_data.get("basic_assumptions_text", ""),
        styles["heading"],
        styles["body"],
        spacing=0.05 * inch,
    )
    append_text_section(
        elements,
        "חישוב הכנסות",
        quote_data.get("revenue_calculation_text", ""),
        styles["heading"],
        styles["body"],
        spacing=0.05 * inch,
    )
    append_text_section(
        elements,
        "סיכום",
        quote_data.get("summary_text", ""),
        styles["heading"],
        styles["body"],
        spacing=0.05 * inch,
    )

    elements.append(
        Paragraph(
            rtl("* כל הנתונים בהצעה משוערים ועשויים להשתנות בהתאם לאתר ההתקנה ולבדיקות הסופיות בשטח."),
            styles["note"],
        )
    )

    elements.append(FrameBreak())
    elements.append(
        build_footer_table(
            company_info or {},
            company_name,
            customer_signature_path,
            styles["footer_right"],
            styles["footer_left"],
            cwd,
            script_dir,
        )
    )

    doc.build(elements)
    buffer.seek(0)
    return buffer


def generate_quote_pdf(quote_data, company_info=None, customer_signature_path=None):
    return generate_quote_pdf_base(
        quote_data,
        company_info=company_info,
        customer_signature_path=customer_signature_path,
        model_type="purchase",
    )


def generate_leasing_quote_pdf(quote_data, company_info=None, customer_signature_path=None):
    return generate_quote_pdf_base(
        quote_data,
        company_info=company_info,
        customer_signature_path=customer_signature_path,
        model_type="leasing",
    )
