from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak, NextPageTemplate, CondPageBreak, FrameBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus.frames import Frame
from reportlab.platypus.doctemplate import PageTemplate, BaseDocTemplate
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

def format_rtl_number_text(text_before, number, text_after=''):
    """
    Format text with embedded numbers for proper RTL display.
    Uses Unicode direction marks to ensure numbers stay in correct position.

    Args:
        text_before: Hebrew text before the number
        number: The number to embed (will be formatted)
        text_after: Hebrew text after the number

    Returns:
        Properly formatted RTL string with embedded number
    """
    # RLM (Right-to-Left Mark) U+200F helps maintain RTL flow
    # LRM (Left-to-Right Mark) U+200E helps isolate LTR content
    RLM = '\u200F'
    LRM = '\u200E'

    # Reshape Hebrew text parts
    reshaped_before = reshape_hebrew(text_before) if text_before else ''
    reshaped_after = reshape_hebrew(text_after) if text_after else ''

    # Format the number and wrap it with direction marks
    number_str = str(format_number(number)) if isinstance(number, (int, float)) else str(number)

    # Combine: Hebrew text + RLM + number + LRM + Hebrew text
    # The RLM before the number keeps it close to the Hebrew text
    # The LRM after helps separate it from following Hebrew
    if reshaped_after:
        result = f"{reshaped_before}{RLM}{number_str}{LRM}{reshaped_after}"
    else:
        result = f"{reshaped_before}{RLM}{number_str}"

    return result

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

def add_blue_background_only(canvas, doc):
    """Add blue background to the entire page (for non-last pages)"""
    canvas.saveState()
    canvas.setFillColor(colors.HexColor('#000080'))  # Blue background
    canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    canvas.restoreState()

def add_blue_background_with_footer(canvas, doc):
    """Add blue background and yellow footer (for last page only)"""
    canvas.saveState()
    # Blue background
    canvas.setFillColor(colors.HexColor('#000080'))
    canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    # Yellow-green footer at bottom
    footer_height = 1.2 * inch
    canvas.setFillColor(colors.HexColor('#D9FF0D'))
    canvas.rect(0, 0, A4[0], footer_height, fill=1, stroke=0)
    canvas.restoreState()

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

        # Create document with blue background
        doc = BaseDocTemplate(
            buffer,
            pagesize=A4,
            topMargin=0.5*inch,
            bottomMargin=0.5*inch,
            leftMargin=0.75*inch,
            rightMargin=0.75*inch
        )

        # Create two page templates: one for regular pages, one for last page with footer
        frame_regular = Frame(
            doc.leftMargin,
            doc.bottomMargin,
            doc.width,
            doc.height,
            id='regular'
        )

        # LastPage has TWO frames: one for content, one for footer in yellow area
        # Frame 1: Main content (same as regular page)
        frame_last_content = Frame(
            doc.leftMargin,
            1.3*inch,  # Start above yellow footer area (which is 0-1.2")
            doc.width,
            doc.height - 0.8*inch,  # Reduced height to accommodate footer frame
            id='last_content'
        )
        # Frame 2: Footer frame positioned exactly in yellow area (0.2" to 1.2" from bottom)
        frame_last_footer = Frame(
            doc.leftMargin,
            0.2*inch,  # Position in yellow area (lower to accommodate more content)
            doc.width,
            1.0*inch,  # Increased height to fit all footer content including signature
            id='last_footer',
            showBoundary=0
        )

        # Template for regular pages (blue background only)
        template_regular = PageTemplate(id='RegularPage', frames=frame_regular, onPage=add_blue_background_only)
        # Template for last page (blue background + yellow footer) with TWO frames
        template_last = PageTemplate(id='LastPage', frames=[frame_last_content, frame_last_footer], onPage=add_blue_background_with_footer)

        doc.addPageTemplates([template_regular, template_last])

        # Container for PDF elements
        elements = []
        styles = getSampleStyleSheet()

        # Custom styles with white text for blue background
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=11,
            textColor=colors.white,  # White text for blue background
            spaceAfter=4,  # Reduced from 6
            spaceBefore=6,  # Reduced from 8
            fontName=FONT_NAME_BOLD,
            alignment=TA_RIGHT  # RTL alignment for Hebrew
        )

        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=9,
            spaceAfter=2,  # Reduced from 3
            textColor=colors.white,  # White text for blue background
            fontName=FONT_NAME,
            alignment=TA_RIGHT  # RTL alignment for Hebrew
        )

        subtitle_style = ParagraphStyle(
            'Subtitle',
            parent=styles['Normal'],
            fontSize=18,
            textColor=colors.white,  # White color for consistency
            spaceAfter=3,
            alignment=TA_CENTER,
            fontName=FONT_NAME_BOLD
        )

        title_style = ParagraphStyle(
            'Title',
            parent=styles['Normal'],
            fontSize=24,
            textColor=colors.HexColor('#D9FF0D'),  # Yellow-green for main heading
            spaceAfter=6,
            alignment=TA_RIGHT,
            fontName=FONT_NAME_BOLD
        )

        # Company header - Blue background with logo and yellow title
        company_name = safe_get(company_info, 'company_name', 'Solar Energy Solutions') if company_info else 'Solar Energy Solutions'

        # Create header with logo on LEFT and title on RIGHT
        # IMPORTANT: Use logo2.png only
        script_dir = os.path.dirname(os.path.abspath(__file__))
        cwd = os.getcwd()

        logo_paths = [
            # Try static/images/logo2.png first (most reliable for Flask apps)
            os.path.join(cwd, 'static', 'images', 'logo2.png'),
            'static/images/logo2.png',
            os.path.join(script_dir, 'static', 'images', 'logo2.png'),
            # Then try root directory
            os.path.join(cwd, 'logo2.png'),
            'logo2.png',
            os.path.join(script_dir, 'logo2.png'),
            # Fallback to logo.png only if logo2.png not found anywhere
            os.path.join(cwd, 'static', 'images', 'logo.png'),
            'static/images/logo.png',
            os.path.join(script_dir, 'static', 'images', 'logo.png')
        ]

        # Debug: Print current working directory and which paths we're trying
        print(f"[DEBUG] Current working directory: {cwd}")
        print(f"[DEBUG] Script directory: {script_dir}")
        print("[DEBUG] Looking for logo in these paths (in order):")
        for p in logo_paths:
            exists = os.path.exists(p)
            print(f"  - {p} {'[EXISTS]' if exists else '[NOT FOUND]'}")

        # Title paragraph for header
        title_hebrew = reshape_hebrew('הצעת מחיר')
        quote_num = str(safe_get(quote_data, 'quote_number', 'N/A'))
        subtitle_hebrew = reshape_hebrew(f'הצעת מחיר מספר {quote_num}')
        safe_title = escape_for_paragraph(title_hebrew)
        safe_subtitle = escape_for_paragraph(subtitle_hebrew)

        # Create title cell content with yellow-green main title and white subtitle
        title_para = Paragraph(f"<para align=right><b><font color='#D9FF0D'>{safe_title}</font></b><br/><font size=12 color='white'>{safe_subtitle}</font></para>", title_style)

        # Try to load logo from multiple paths
        logo_loaded = False
        for logo_path in logo_paths:
            if os.path.exists(logo_path):
                try:
                    logo = Image(logo_path, width=2.2*inch, height=0.9*inch, kind='proportional')
                    # Header with logo on LEFT, title on RIGHT
                    header_data = [[logo, title_para]]
                    header_table = Table(header_data, colWidths=[2.5*inch, 4*inch])
                    header_table.setStyle(TableStyle([
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('ALIGN', (0, 0), (0, 0), 'LEFT'),    # Logo aligned left
                        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),   # Title aligned right
                        ('TOPPADDING', (0, 0), (-1, -1), 15),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
                        ('LEFTPADDING', (0, 0), (-1, -1), 20),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 20),
                    ]))
                    elements.append(header_table)
                    print(f"[OK] Logo loaded from: {logo_path}")
                    logo_loaded = True
                    break
                except Exception as e:
                    print(f"[ERROR] Error loading logo from {logo_path}: {e}")
                    continue

        if not logo_loaded:
            print(f"[WARNING] Logo not found in any of these paths: {logo_paths}")
            # Fallback: Just show title
            title_para = Paragraph(f"<para align=center>{safe_title}</para>", title_style)
            elements.append(title_para)

        elements.append(Spacer(1, 0.1*inch))  # Reduced spacing

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
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),  # White text for blue background
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        quote_table.hAlign = 'RIGHT'  # Align table to the right margin
        elements.append(quote_table)
        elements.append(Spacer(1, 0.06*inch))  # Reduced spacing

        # Customer Information
        customer_heading = Paragraph(escape_for_paragraph(reshape_hebrew("פרטי לקוח")), heading_style)
        elements.append(customer_heading)
        elements.append(Spacer(1, 0.06*inch))  # Reduced spacing

        customer_name_val = safe_get(quote_data, 'customer_name', '')
        customer_phone_val = safe_get(quote_data, 'customer_phone', '')
        customer_email_val = safe_get(quote_data, 'customer_email', '')
        customer_address_val = safe_get(quote_data, 'customer_address', '')

        not_specified = reshape_hebrew('לא צוין')

        # Apply reshape_hebrew to customer values for proper RTL display
        customer_name_display = reshape_hebrew(customer_name_val) if customer_name_val else not_specified
        customer_phone_display = customer_phone_val if customer_phone_val else not_specified  # Phone numbers don't need reshaping
        customer_email_display = customer_email_val if customer_email_val else not_specified  # Email doesn't need reshaping
        customer_address_display = reshape_hebrew(customer_address_val) if customer_address_val else not_specified

        # RTL: Value first (right), Label second (left)
        customer_data = [
            [customer_name_display, reshape_hebrew('שם:')],
            [customer_phone_display, reshape_hebrew('טלפון:')],
            [customer_email_display, reshape_hebrew('אימייל:')],
            [customer_address_display, reshape_hebrew('כתובת:')],
        ]

        customer_table = Table(customer_data, colWidths=[4.8*inch, 1.2*inch])
        customer_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), FONT_NAME),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),  # White text
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),  # RTL alignment
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(customer_table)
        elements.append(Spacer(1, 0.06*inch))  # Reduced spacing

        # System Specifications
        specs_heading = Paragraph(escape_for_paragraph(reshape_hebrew("מפרט מערכת")), heading_style)
        elements.append(specs_heading)
        elements.append(Spacer(1, 0.06*inch))  # Reduced spacing

        system_size = quote_data.get('system_size', 0) or 0
        roof_area = quote_data.get('roof_area')
        annual_prod = quote_data.get('annual_production', 0) or 0

        # RTL: Value first (right), Label second (left)
        # Use RLM (Right-to-Left Mark) for proper number alignment
        RLM = '\u200F'
        specs_data = [
            [f"{RLM}{system_size} {reshape_hebrew('קוט״ש')}", reshape_hebrew('גודל מערכת:')],
            [f"{RLM}{roof_area} {reshape_hebrew('מ״ר')}" if roof_area else not_specified, reshape_hebrew('שטח גג:')],
            [f"{RLM}{format_number(annual_prod)} {reshape_hebrew('קוט״ש/שנה')}" if annual_prod else not_specified, reshape_hebrew('ייצור שנתי:')],
            [safe_get(quote_data, 'panel_type') or not_specified, reshape_hebrew('סוג פאנל:')],
            [f"{RLM}{str(safe_get(quote_data, 'panel_count'))}" if safe_get(quote_data, 'panel_count') else not_specified, reshape_hebrew('מספר פאנלים:')],
            [safe_get(quote_data, 'inverter_type') or not_specified, reshape_hebrew('סוג ממיר:')],
            [safe_get(quote_data, 'direction') or not_specified, reshape_hebrew('כיוון:')],
            [f"{RLM}{quote_data.get('tilt_angle')}°" if quote_data.get('tilt_angle') else not_specified, reshape_hebrew('זווית הטיה:')],
            [f"{RLM}{quote_data.get('warranty_years', 25)} {reshape_hebrew('שנים')}", reshape_hebrew('אחריות:')],
        ]

        specs_table = Table(specs_data, colWidths=[3.8*inch, 2.2*inch])
        specs_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), FONT_NAME),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),  # White text
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),  # RTL alignment
            ('GRID', (0, 0), (-1, -1), 0.5, colors.white),  # White grid lines
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(specs_table)
        elements.append(Spacer(1, 0.06*inch))  # Reduced spacing

        # Get financial data
        total_price = quote_data.get('total_price', 0) or 0
        annual_revenue = quote_data.get('annual_revenue', 0) or 0

        # Production Charts Section
        if system_size and annual_prod:
            elements.append(Spacer(1, 0.05*inch))  # Reduced spacing

            # Monthly Production Chart
            chart_heading = Paragraph(escape_for_paragraph(reshape_hebrew("ייצור אנרגיה חודשי")), heading_style)
            elements.append(chart_heading)
            elements.append(Spacer(1, 0.04*inch))  # Reduced spacing

            try:
                monthly_chart_bytes = generate_monthly_production_chart(system_size, annual_prod)
                # Increased height slightly to push directional chart heading to page 2
                monthly_chart_img = Image(BytesIO(monthly_chart_bytes), width=6.5*inch, height=2.85*inch)
                elements.append(monthly_chart_img)
                elements.append(Spacer(1, 0.04*inch))  # Reduced spacing
            except Exception as e:
                print(f"[ERROR] Error generating monthly chart: {e}")

            # Directional Production Chart - maintain square aspect ratio
            try:
                directional_heading = Paragraph(escape_for_paragraph(reshape_hebrew("ייצור לפי כיוון גג")), heading_style)
                elements.append(directional_heading)
                elements.append(Spacer(1, 0.04*inch))  # Reduced spacing
                directional_chart_bytes = generate_directional_production_chart(system_size, annual_prod)
                # Increased size for better visibility
                directional_chart_img = Image(BytesIO(directional_chart_bytes), width=4.5*inch, height=4.5*inch)
                elements.append(directional_chart_img)
                elements.append(Spacer(1, 0.04*inch))  # Reduced spacing
            except Exception as e:
                print(f"[ERROR] Error generating directional chart: {e}")

        # Financial Summary
        financial_heading = Paragraph(escape_for_paragraph(reshape_hebrew("סיכום פיננסי")), heading_style)
        elements.append(financial_heading)
        elements.append(Spacer(1, 0.06*inch))  # Reduced spacing

        payback = quote_data.get('payback_period', 0) or 0

        # RTL: Value first (right), Label second (left)
        # Use RLM for proper currency and number alignment
        RLM = '\u200F'
        financial_data = [
            [reshape_hebrew('סכום'), reshape_hebrew('תיאור')],
            [f"{RLM}₪{format_number(total_price)}", reshape_hebrew('סך ההשקעה')],
            [f"{RLM}₪{format_number(annual_revenue)}", reshape_hebrew('הכנסה שנתית משוערת')],
            [f"{RLM}{payback} {reshape_hebrew('שנים')}", reshape_hebrew('תקופת החזר')],
            [f"{RLM}₪{format_number(annual_revenue * 25)}", reshape_hebrew('חיסכון כולל ל-25 שנה')],
        ]

        financial_table = Table(financial_data, colWidths=[2.5*inch, 3.5*inch])
        financial_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.white),  # White header
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#2d3748')),  # Dark text on white header
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.white),  # White text for data rows
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),  # RTL alignment for all cells
            ('FONTNAME', (0, 0), (-1, -1), FONT_NAME),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.7, colors.white),  # White grid lines
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(financial_table)
        elements.append(Spacer(1, 0.06*inch))  # Reduced spacing

        # Calculate financial metrics here (moved from later in the code)
        RLM = '\u200F'
        price_per_kwp = (total_price / 1.18) / system_size if system_size else 0
        roa = ((annual_revenue / total_price) * 100) if total_price else 0

        # Financial Metrics Summary on Page 2
        metrics_heading = Paragraph(escape_for_paragraph(reshape_hebrew("מדדים פיננסיים - סיכום השקעה")), heading_style)
        elements.append(metrics_heading)
        elements.append(Spacer(1, 0.06*inch))

        metrics_data = [
            [reshape_hebrew('ערך'), reshape_hebrew('מדד')],
            [f"{RLM}₪{format_number(int(total_price))}", reshape_hebrew('עלות כוללת (כולל מע״מ)')],
            [f"{RLM}₪{format_number(int(price_per_kwp))}", reshape_hebrew('מחיר לקילו-וואט')],
            [f"{RLM}{roa:.1f}%", reshape_hebrew('תשואה שנתית (ROA)')],
            [f"{RLM}{payback:.2f}", reshape_hebrew('תקופת החזר (שנים)')],
        ]

        metrics_table = Table(metrics_data, colWidths=[2.0*inch, 4.0*inch])
        metrics_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.white),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#2d3748')),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), FONT_NAME_BOLD),
            ('FONTNAME', (0, 1), (-1, -1), FONT_NAME),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.white),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(metrics_table)
        elements.append(Spacer(1, 0.08*inch))

        # Environmental Impact
        env_heading = Paragraph(escape_for_paragraph(reshape_hebrew("השפעה סביבתית")), heading_style)
        elements.append(env_heading)
        elements.append(Spacer(1, 0.06*inch))

        trees = int(annual_prod * 0.05) if annual_prod else 0
        co2_saved = int(annual_prod * 0.5) if annual_prod else 0

        # Build environmental text with proper RTL formatting for numbers
        part1 = format_rtl_number_text('המערכת הסולארית שלך תייצר כ-', annual_prod, ' קוט״ש של אנרגיה נקייה בשנה, שווה ערך לנטיעת ')
        part2 = format_rtl_number_text('', trees, ' עצים והפחתת פליטות CO2 ב-')
        part3 = format_rtl_number_text('', co2_saved, ' ק״ג בשנה. במשך 25 שנה, זהו תרומה משמעותית לקיימות סביבתית.')

        env_text = escape_for_paragraph(part1 + part2 + part3)
        env_para = Paragraph(env_text, normal_style)
        elements.append(env_para)
        elements.append(Spacer(1, 0.1*inch))

        # Switch to LastPage template for page 3 which has yellow footer
        elements.append(NextPageTemplate('LastPage'))
        # Page break to Page 3
        elements.append(PageBreak())

        # Cash Flow Analysis Section - Page 3
        cashflow_heading = Paragraph(escape_for_paragraph(reshape_hebrew("ניתוח תזרים מזומנים - 25 שנה")), heading_style)
        elements.append(cashflow_heading)
        elements.append(Spacer(1, 0.08*inch))

        # Calculate cash flow data
        degradation_rate = 0.004
        base_operating_cost = total_price * 0.005
        cumulative_cashflow = -total_price

        # RLM mark for proper number alignment
        RLM = '\u200F'

        # Build cash flow table data
        cashflow_table_data = []
        # Header row
        cashflow_table_data.append([
            reshape_hebrew('תזרים מצטבר'),
            reshape_hebrew('רווח נקי'),
            reshape_hebrew('תפעול'),
            reshape_hebrew('הכנסה'),
            reshape_hebrew('השקעה'),
            reshape_hebrew('שנה')
        ])

        # Year 0
        cashflow_table_data.append([
            f"{RLM}₪{format_number(int(-total_price))}",
            '-',
            '-',
            '-',
            f"{RLM}₪{format_number(int(-total_price))}",
            f"{RLM}0"
        ])

        total_revenue_sum = 0
        total_operating_sum = 0
        total_net_profit_sum = 0

        # Years 1-25
        for year in range(1, 26):
            yearly_degradation = 1 - (degradation_rate * (year - 1))
            year_revenue = int(annual_revenue * yearly_degradation)
            year_operating_cost = int(base_operating_cost * (1.02 ** (year - 1)))
            year_net_profit = year_revenue - year_operating_cost

            total_revenue_sum += year_revenue
            total_operating_sum += year_operating_cost
            total_net_profit_sum += year_net_profit
            cumulative_cashflow = total_net_profit_sum - total_price

            cashflow_table_data.append([
                f"{RLM}₪{format_number(cumulative_cashflow)}",
                f"{RLM}₪{format_number(year_net_profit)}",
                f"{RLM}₪{format_number(year_operating_cost)}",
                f"{RLM}₪{format_number(year_revenue)}",
                '-',
                f"{RLM}{str(year)}"
            ])

        # Total row
        cashflow_table_data.append([
            f"{RLM}₪{format_number(cumulative_cashflow)}",
            f"{RLM}₪{format_number(total_net_profit_sum)}",
            f"{RLM}₪{format_number(total_operating_sum)}",
            f"{RLM}₪{format_number(total_revenue_sum)}",
            f"{RLM}₪{format_number(int(-total_price))}",
            reshape_hebrew('סה״כ')
        ])

        # Create cash flow table (smaller font to fit all rows)
        cashflow_table = Table(cashflow_table_data, colWidths=[1.0*inch, 1.0*inch, 0.9*inch, 1.0*inch, 1.0*inch, 0.6*inch])
        cashflow_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.white),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#2d3748')),
            ('TEXTCOLOR', (0, 1), (-1, -2), colors.white),
            ('BACKGROUND', (0, -1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.HexColor('#2d3748')),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), FONT_NAME_BOLD),
            ('FONTNAME', (0, 1), (-1, -1), FONT_NAME),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('FONTSIZE', (0, 1), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.white),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(cashflow_table)
        elements.append(Spacer(1, 0.08*inch))

        # Assumptions note
        assumptions_heading = Paragraph(escape_for_paragraph(reshape_hebrew("הנחות יסוד")), heading_style)
        elements.append(assumptions_heading)
        elements.append(Spacer(1, 0.04*inch))

        # Build assumptions text with proper RTL formatting for numbers
        RLM = '\u200F'
        assumptions_parts = [
            reshape_hebrew('ירידה שנתית בייצור: '),
            f"{RLM}0.4%",
            reshape_hebrew(' | עלויות תפעול: '),
            f"{RLM}0.5%",
            reshape_hebrew(' עלות המערכת, עלייה '),
            f"{RLM}2%",
            reshape_hebrew(' בשנה | מחירי תעריפים עפ״י תקנות ייצור פרטי | אחריות: '),
            f"{RLM}25",
            reshape_hebrew(' שנה')
        ]
        assumptions_text = ''.join(assumptions_parts)
        assumptions_para = Paragraph(escape_for_paragraph(assumptions_text), ParagraphStyle(
            'Assumptions',
            parent=normal_style,
            fontSize=8,
            textColor=colors.white,
            alignment=TA_RIGHT,
            fontName=FONT_NAME,
            spaceAfter=10
        ))
        elements.append(assumptions_para)
        elements.append(Spacer(1, 0.1*inch))

        # Closing remarks
        closing_heading = Paragraph(escape_for_paragraph(reshape_hebrew("סיכום")), heading_style)
        elements.append(closing_heading)
        elements.append(Spacer(1, 0.04*inch))

        total_cashflow_25 = cumulative_cashflow
        closing_text = format_rtl_number_text(
            'השקעה במערכת סולארית היא השקעה חכמה לטווח ארוך. על פי החישובים, התזרים המצטבר ל-25 שנה הוא ',
            total_cashflow_25,
            f' ש״ח, מה שמעיד על רווחיות גבוהה. נשמח לעמוד לשירותכם בכל שאלה.'
        )
        closing_para = Paragraph(escape_for_paragraph(closing_text), normal_style)
        elements.append(closing_para)

        # Break to footer frame - this moves content to the footer frame positioned in yellow area
        elements.append(FrameBreak())

        # Footer text (will appear in footer frame positioned on yellow background)
        # Using two-column layout: company info on right, signature on left
        footer_style_right = ParagraphStyle(
            'FooterRight',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#2d3748'),  # Dark gray text on yellow-green
            alignment=TA_RIGHT,
            leading=10,
            fontName=FONT_NAME
        )

        footer_style_left = ParagraphStyle(
            'FooterLeft',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#2d3748'),
            alignment=TA_LEFT,
            leading=10,
            fontName=FONT_NAME
        )

        # Right column: Company information
        right_lines = []
        right_lines.append(f"<b>{escape_for_paragraph(company_name)}</b>")

        if company_info:
            if company_info.get('company_phone'):
                # RTL: Phone number on left, label on right
                right_lines.append(escape_for_paragraph(company_info['company_phone']) + ' :' + escape_for_paragraph(reshape_hebrew('טלפון')))
            if company_info.get('company_email'):
                # RTL: Email on left, label on right
                right_lines.append(escape_for_paragraph(company_info['company_email']) + ' :' + escape_for_paragraph(reshape_hebrew('אימייל')))
            if company_info.get('company_address'):
                # RTL: Address on left, label on right
                right_lines.append(escape_for_paragraph(reshape_hebrew(company_info['company_address'])) + ' :' + escape_for_paragraph(reshape_hebrew('כתובת')))

        right_lines.append("")
        right_lines.append(escape_for_paragraph(reshape_hebrew('כאן לשירותך וזמינה לשאלות ובירורים.')))

        right_text = "<br/>".join(right_lines)
        right_para = Paragraph(right_text, footer_style_right)

        # Left column: Signature line (longer underscore)
        left_text = escape_for_paragraph(reshape_hebrew('חתימה: _______________________'))
        left_para = Paragraph(left_text, footer_style_left)

        # Create two-column footer table: signature on left, company info on right
        footer_data = [[left_para, right_para]]
        footer_table = Table(footer_data, colWidths=[2.5*inch, 3.5*inch])
        footer_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (0, 0), 'BOTTOM'),  # Signature at bottom
            ('VALIGN', (1, 0), (1, 0), 'TOP'),      # Company info at top
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('LEFTPADDING', (0, 0), (0, 0), 0),     # Remove left padding for signature
            ('RIGHTPADDING', (1, 0), (1, 0), 0),    # Remove right padding to align with text margin
        ]))

        # Add footer table - FrameBreak above ensures it goes into footer frame on yellow background
        elements.append(footer_table)

        # Build PDF
        doc.build(elements)
        buffer.seek(0)
        return buffer

    except Exception as e:
        print(f"[ERROR] Error building PDF: {e}")
        traceback.print_exc()
        raise
