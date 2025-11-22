from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from io import BytesIO
from datetime import datetime, timedelta
from chart_generator import generate_monthly_production_chart, generate_directional_production_chart
import os
import traceback

# Try to import libraries for proper RTL text handling
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    RTL_AVAILABLE = True
    print("[OK] RTL text libraries loaded for PDF (arabic_reshaper + bidi)")
except ImportError as e:
    RTL_AVAILABLE = False
    print(f"[WARNING] RTL text libraries not available for PDF: {e}")
    print("[INFO] Install with: pip install arabic-reshaper python-bidi")
    def get_display(text):
        return text

def reshape_hebrew(text):
    """
    Reshape Hebrew text for proper RTL display in PDF.
    Uses two-step process: arabic_reshaper + bidi algorithm.
    """
    if text is None:
        return ''

    # Ensure text is a string
    text_str = str(text)
    if text_str == 'None' or text_str == '':
        return ''

    # Ensure text is properly encoded as UTF-8
    try:
        # If it's bytes, decode it
        if isinstance(text_str, bytes):
            text_str = text_str.decode('utf-8')
        # Ensure it can be encoded/decoded properly
        text_str = text_str.encode('utf-8', errors='ignore').decode('utf-8')
    except Exception as e:
        print(f"[WARNING] Text encoding error: {e}")

    if RTL_AVAILABLE:
        try:
            # Step 1: Reshape the text (handles character connections)
            reshaped_text = arabic_reshaper.reshape(text_str)
            # Step 2: Apply bidi algorithm for proper RTL display
            bidi_text = get_display(reshaped_text)
            return bidi_text
        except Exception as e:
            print(f"[WARNING] RTL text processing error: {e}")
            return text_str
    return text_str

# Register Hebrew-supporting font
def register_hebrew_font():
    """Register a Hebrew-supporting font for PDF generation"""
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    bundled_font_dir = os.path.join(script_dir, 'fonts')

    font_paths = [
        # Bundled Heebo fonts (highest priority - designed for Hebrew with full Latin support)
        (os.path.join(bundled_font_dir, 'Heebo-Regular.ttf'),
         os.path.join(bundled_font_dir, 'Heebo-Bold.ttf')),
        # Bundled Rubik fonts (backup)
        (os.path.join(bundled_font_dir, 'Rubik-Regular.ttf'),
         os.path.join(bundled_font_dir, 'Rubik-Bold.ttf')),
        # Windows fonts - Arial (has Hebrew support)
        ('C:/Windows/Fonts/arial.ttf', 'C:/Windows/Fonts/arialbd.ttf'),
        ('C:/Windows/Fonts/ARIAL.TTF', 'C:/Windows/Fonts/ARIALBD.TTF'),
        # Tahoma (has Hebrew support)
        ('C:/Windows/Fonts/tahoma.ttf', 'C:/Windows/Fonts/tahomabd.ttf'),
        # Linux system fonts - DejaVuSans has good Hebrew + Latin coverage
        ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
        ('/usr/share/fonts/truetype/freefont/FreeSans.ttf', '/usr/share/fonts/truetype/freefont/FreeSansBold.ttf'),
    ]

    for regular_path, bold_path in font_paths:
        if os.path.exists(regular_path):
            try:
                pdfmetrics.registerFont(TTFont('Hebrew', regular_path))
                print(f"[OK] Registered Hebrew font: {regular_path}")

                if os.path.exists(bold_path):
                    pdfmetrics.registerFont(TTFont('Hebrew-Bold', bold_path))
                    print(f"[OK] Registered Hebrew-Bold font: {bold_path}")
                else:
                    pdfmetrics.registerFont(TTFont('Hebrew-Bold', regular_path))
                    print(f"[OK] Using regular font for bold: {regular_path}")

                return True
            except Exception as e:
                print(f"[ERROR] Error registering font {regular_path}: {e}")
                traceback.print_exc()
                continue

    print("[WARNING] No Hebrew font found. PDF will use default font.")
    return False

# Register fonts on module load
HEBREW_FONT_AVAILABLE = register_hebrew_font()
FONT_NAME = 'Hebrew' if HEBREW_FONT_AVAILABLE else 'Helvetica'
FONT_NAME_BOLD = 'Hebrew-Bold' if HEBREW_FONT_AVAILABLE else 'Helvetica-Bold'

print(f"[INFO] Using font: {FONT_NAME}, Bold: {FONT_NAME_BOLD}")

def safe_get(data, key, default=''):
    """Safely get a value from dictionary, handling None values and encoding"""
    value = data.get(key)
    if value is None or str(value) == 'None' or value == '':
        return default

    # Ensure proper UTF-8 encoding for string values
    if isinstance(value, str):
        try:
            # Clean and ensure UTF-8 encoding
            value = value.encode('utf-8', errors='ignore').decode('utf-8')
        except Exception as e:
            print(f"[WARNING] Encoding error for key '{key}': {e}")

    return value

def format_number(num):
    """Format number with thousands separator"""
    try:
        return f"{int(num):,}"
    except:
        return str(num)

def escape_for_paragraph(text):
    """
    Escape text for use in ReportLab Paragraph with proper encoding.
    This prevents latin-1 encoding errors.
    """
    if text is None:
        return ''

    text_str = str(text)

    # Ensure UTF-8 encoding
    try:
        if isinstance(text_str, bytes):
            text_str = text_str.decode('utf-8', errors='replace')
        # Normalize the text to ensure compatibility
        text_str = text_str.encode('utf-8', errors='replace').decode('utf-8')
    except Exception as e:
        print(f"[WARNING] Text escape error: {e}")
        return ''

    # Escape XML special characters that Paragraph uses
    text_str = text_str.replace('&', '&amp;')
    text_str = text_str.replace('<', '&lt;')
    text_str = text_str.replace('>', '&gt;')

    return text_str

def generate_quote_pdf(quote_data, company_info=None):
    """
    Generate a professional PDF quote with Hebrew support

    Args:
        quote_data: Dictionary containing quote information
        company_info: Dictionary containing company information

    Returns:
        BytesIO object containing the PDF
    """
    try:
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            topMargin=0.5*inch,
            bottomMargin=0.5*inch,
            leftMargin=0.75*inch,
            rightMargin=0.75*inch
        )

        # Container for PDF elements
        elements = []
        styles = getSampleStyleSheet()

        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#2d3748'),
            spaceAfter=6,
            alignment=TA_CENTER,
            fontName=FONT_NAME_BOLD
        )

        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=11,
            textColor=colors.HexColor('#00358A'),
            spaceAfter=8,
            spaceBefore=12,
            fontName=FONT_NAME_BOLD,
            alignment=TA_RIGHT  # RTL alignment for Hebrew
        )

        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=9,
            spaceAfter=4,
            fontName=FONT_NAME,
            alignment=TA_RIGHT  # RTL alignment for Hebrew
        )

        subtitle_style = ParagraphStyle(
            'Subtitle',
            parent=styles['Normal'],
            fontSize=12,
            textColor=colors.HexColor('#00358A'),
            spaceAfter=4,
            alignment=TA_CENTER,
            fontName=FONT_NAME_BOLD
        )

        # Company header
        company_name = safe_get(company_info, 'company_name', 'Solar Energy Solutions') if company_info else 'Solar Energy Solutions'

        # Add company logo from uploads directory
        logo_path = 'static/images/logo.png'

        if os.path.exists(logo_path):
            try:
                logo = Image(logo_path, width=2.5*inch, height=1*inch, kind='proportional')
                logo.hAlign = 'CENTER'
                elements.append(logo)
                elements.append(Spacer(1, 0.2*inch))
                print(f"[OK] Logo loaded from: {logo_path}")
            except Exception as e:
                print(f"[ERROR] Error loading logo: {e}")
        else:
            print(f"[WARNING] Logo not found at: {logo_path}")

        # Title - Removed since we have logo now
        # safe_company_name = escape_for_paragraph(company_name)
        # title = Paragraph(f"<para align=center><b>{safe_company_name}</b></para>", title_style)
        # elements.append(title)

        # Subtitle in Hebrew
        subtitle_hebrew = reshape_hebrew('הצעת מחיר אנרגיה סולארית')
        safe_subtitle = escape_for_paragraph(subtitle_hebrew)
        subtitle = Paragraph(f"<para align=center>{safe_subtitle}</para>", subtitle_style)
        elements.append(subtitle)
        elements.append(Spacer(1, 0.15*inch))

        # Quote number and date
        today = datetime.now()
        valid_until = today + timedelta(days=30)

        # RTL: Value first (right), Label second (left)
        quote_info = [
            [str(safe_get(quote_data, 'quote_number', 'N/A')), reshape_hebrew('מספר הצעה:')],
            [today.strftime('%d/%m/%Y'), reshape_hebrew('תאריך:')],
            [valid_until.strftime('%d/%m/%Y'), reshape_hebrew('בתוקף עד:')]
        ]

        quote_table = Table(quote_info, colWidths=[2.5*inch, 1.5*inch])
        quote_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),  # RTL alignment for all cells
            ('FONTNAME', (0, 0), (-1, -1), FONT_NAME),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#4a5568')),  # Labels on left
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        elements.append(quote_table)
        elements.append(Spacer(1, 0.12*inch))

        # Customer Information
        customer_heading = Paragraph(escape_for_paragraph(reshape_hebrew("פרטי לקוח")), heading_style)
        elements.append(customer_heading)
        elements.append(Spacer(1, 0.08*inch))

        customer_name_val = safe_get(quote_data, 'customer_name', '')
        customer_phone_val = safe_get(quote_data, 'customer_phone', '')
        customer_email_val = safe_get(quote_data, 'customer_email', '')
        customer_address_val = safe_get(quote_data, 'customer_address', '')

        not_specified = reshape_hebrew('לא צוין')

        # RTL: Value first (right), Label second (left)
        customer_data = [
            [customer_name_val if customer_name_val else not_specified, reshape_hebrew('שם:')],
            [customer_phone_val if customer_phone_val else not_specified, reshape_hebrew('טלפון:')],
            [customer_email_val if customer_email_val else not_specified, reshape_hebrew('אימייל:')],
            [customer_address_val if customer_address_val else not_specified, reshape_hebrew('כתובת:')],
        ]

        customer_table = Table(customer_data, colWidths=[4.8*inch, 1.2*inch])
        customer_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), FONT_NAME),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#4a5568')),  # Values
            ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#2d3748')),  # Labels (darker)
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),  # RTL alignment
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LINEBELOW', (0, 0), (-1, -2), 0.5, colors.HexColor('#e2e8f0')),
            ('LINEBELOW', (0, -1), (-1, -1), 1, colors.HexColor('#cbd5e0')),
        ]))
        elements.append(customer_table)
        elements.append(Spacer(1, 0.12*inch))

        # System Specifications
        specs_heading = Paragraph(escape_for_paragraph(reshape_hebrew("מפרט מערכת")), heading_style)
        elements.append(specs_heading)
        elements.append(Spacer(1, 0.08*inch))

        system_size = quote_data.get('system_size', 0) or 0
        roof_area = quote_data.get('roof_area')
        annual_prod = quote_data.get('annual_production', 0) or 0

        # RTL: Value first (right), Label second (left)
        specs_data = [
            [reshape_hebrew(f"{system_size} " + 'קוט״ש'), reshape_hebrew('גודל מערכת:')],
            [reshape_hebrew(f"{roof_area} " + 'מ״ר') if roof_area else not_specified, reshape_hebrew('שטח גג:')],
            [reshape_hebrew(f"{format_number(annual_prod)} " + 'קוט״ש/שנה') if annual_prod else not_specified, reshape_hebrew('ייצור שנתי:')],
            [safe_get(quote_data, 'panel_type') or not_specified, reshape_hebrew('סוג פאנל:')],
            [str(safe_get(quote_data, 'panel_count')) if safe_get(quote_data, 'panel_count') else not_specified, reshape_hebrew('מספר פאנלים:')],
            [safe_get(quote_data, 'inverter_type') or not_specified, reshape_hebrew('סוג ממיר:')],
            [safe_get(quote_data, 'direction') or not_specified, reshape_hebrew('כיוון:')],
            [f"{quote_data.get('tilt_angle')}°" if quote_data.get('tilt_angle') else not_specified, reshape_hebrew('זווית הטיה:')],
            [reshape_hebrew(f"{quote_data.get('warranty_years', 25)} " + 'שנים'), reshape_hebrew('אחריות:')],
        ]

        specs_table = Table(specs_data, colWidths=[3.8*inch, 2.2*inch])
        specs_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), FONT_NAME),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#4a5568')),  # Values
            ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#2d3748')),  # Labels (darker)
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),  # RTL alignment
            ('GRID', (0, 0), (-1, -1), 0.75, colors.HexColor('#e2e8f0')),
            ('BACKGROUND', (1, 0), (1, -1), colors.HexColor('#f7fafc')),  # Labels column background
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(specs_table)
        elements.append(Spacer(1, 0.12*inch))

        # Get financial data
        total_price = quote_data.get('total_price', 0) or 0
        annual_revenue = quote_data.get('annual_revenue', 0) or 0

        # Production Charts Section
        if system_size and annual_prod:
            elements.append(Spacer(1, 0.12*inch))

            # Monthly Production Chart
            chart_heading = Paragraph(escape_for_paragraph(reshape_hebrew("ייצור אנרגיה חודשי")), heading_style)
            elements.append(chart_heading)
            elements.append(Spacer(1, 0.08*inch))

            try:
                monthly_chart_bytes = generate_monthly_production_chart(system_size, annual_prod)
                monthly_chart_img = Image(BytesIO(monthly_chart_bytes), width=6.8*inch, height=3.0*inch)
                elements.append(monthly_chart_img)
                elements.append(Spacer(1, 0.15*inch))
            except Exception as e:
                print(f"[ERROR] Error generating monthly chart: {e}")

            # Directional Production Chart - maintain square aspect ratio
            try:
                directional_heading = Paragraph(escape_for_paragraph(reshape_hebrew("ייצור לפי כיוון גג")), heading_style)
                elements.append(directional_heading)
                elements.append(Spacer(1, 0.08*inch))
                directional_chart_bytes = generate_directional_production_chart(system_size, annual_prod)
                # Use square aspect ratio for the compass chart
                directional_chart_img = Image(BytesIO(directional_chart_bytes), width=4.2*inch, height=4.2*inch)
                elements.append(directional_chart_img)
                elements.append(Spacer(1, 0.15*inch))
            except Exception as e:
                print(f"[ERROR] Error generating directional chart: {e}")

        # Financial Summary
        financial_heading = Paragraph(escape_for_paragraph(reshape_hebrew("סיכום פיננסי")), heading_style)
        elements.append(financial_heading)
        elements.append(Spacer(1, 0.08*inch))

        payback = quote_data.get('payback_period', 0) or 0

        # RTL: Value first (right), Label second (left)
        financial_data = [
            [reshape_hebrew('סכום'), reshape_hebrew('תיאור')],
            [f"₪{format_number(total_price)}", reshape_hebrew('סך ההשקעה')],
            [f"₪{format_number(annual_revenue)}", reshape_hebrew('הכנסה שנתית משוערת')],
            [reshape_hebrew(f"{payback} " + 'שנים'), reshape_hebrew('תקופת החזר')],
            [f"₪{format_number(annual_revenue * 25)}", reshape_hebrew('חיסכון כולל ל-25 שנה')],
        ]

        financial_table = Table(financial_data, colWidths=[2.5*inch, 3.5*inch])
        financial_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#00358A')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),  # RTL alignment for all cells
            ('FONTNAME', (0, 0), (-1, -1), FONT_NAME),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e0')),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f7fafc')),
            ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#f7fafc')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(financial_table)
        elements.append(Spacer(1, 0.12*inch))

        # Environmental Impact
        env_heading = Paragraph(escape_for_paragraph(reshape_hebrew("השפעה סביבתית")), heading_style)
        elements.append(env_heading)
        elements.append(Spacer(1, 0.08*inch))

        trees = int(annual_prod * 0.05) if annual_prod else 0
        co2_saved = int(annual_prod * 0.5) if annual_prod else 0

        # Build environmental text with proper encoding
        env_text_parts = [
            reshape_hebrew('המערכת הסולארית שלך תייצר כ-'),
            str(format_number(annual_prod)),
            reshape_hebrew(' קוט״ש של אנרגיה נקייה בשנה, שווה ערך לנטיעת '),
            str(format_number(trees)),
            reshape_hebrew(' עצים והפחתת פליטות CO2 ב-'),
            str(format_number(co2_saved)),
            reshape_hebrew(' ק״ג בשנה. במשך 25 שנה, זהו תרומה משמעותית לקיימות סביבתית.')
        ]

        # Ensure each part is properly encoded before joining
        safe_env_parts = [escape_for_paragraph(part) for part in env_text_parts]
        env_text = ''.join(safe_env_parts)

        env_para = Paragraph(env_text, normal_style)
        elements.append(env_para)
        elements.append(Spacer(1, 0.2*inch))

        # Footer
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=7,
            textColor=colors.HexColor('#718096'),
            alignment=TA_CENTER,
            leading=10,
            fontName=FONT_NAME
        )

        footer_lines = [f"<b>{escape_for_paragraph(company_name)}</b>"]

        if company_info:
            if company_info.get('company_phone'):
                footer_lines.append(escape_for_paragraph(company_info['company_phone']))
            if company_info.get('company_email'):
                footer_lines.append(escape_for_paragraph(company_info['company_email']))
            if company_info.get('company_address'):
                footer_lines.append(escape_for_paragraph(company_info['company_address']))

        footer_lines.append("")
        footer_lines.append(f"<i>{escape_for_paragraph(reshape_hebrew('הצעה זו בתוקף 30 ימים מתאריך ההנפקה.'))}</i>")
        footer_lines.append(escape_for_paragraph(reshape_hebrew('תודה שבחרתם באנרגיה סולארית!')))

        footer_text = "<para align=center>" + "<br/>".join(footer_lines) + "</para>"
        footer = Paragraph(footer_text, footer_style)
        elements.append(footer)

        # Build PDF
        doc.build(elements)
        buffer.seek(0)
        return buffer

    except Exception as e:
        print(f"[ERROR] Error building PDF: {e}")
        traceback.print_exc()
        raise
