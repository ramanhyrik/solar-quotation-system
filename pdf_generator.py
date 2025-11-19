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
from chart_generator import generate_monthly_production_chart, generate_payback_chart
import os
import traceback

# Try to import bidi for proper RTL text handling
try:
    from bidi.algorithm import get_display
    BIDI_AVAILABLE = True
    print("[OK] Bidi library loaded successfully")
except ImportError:
    BIDI_AVAILABLE = False
    print("[WARNING] Bidi library not available - Hebrew text may not display correctly")
    print("[INFO] Install with: pip install python-bidi")
    def get_display(text):
        return text

def reshape_hebrew(text):
    """Reshape Hebrew text for proper RTL display in PDF"""
    if text is None:
        return ''
    text_str = str(text)
    if text_str == 'None':
        return ''
    if BIDI_AVAILABLE:
        try:
            return get_display(text_str)
        except Exception as e:
            print(f"[WARNING] Bidi processing error: {e}")
            return text_str
    return text_str

# Register Hebrew-supporting font
def register_hebrew_font():
    """Register a Hebrew-supporting font for PDF generation"""
    font_paths = [
        # Windows fonts - Arial is best for Hebrew
        ('C:/Windows/Fonts/arial.ttf', 'C:/Windows/Fonts/arialbd.ttf'),
        ('C:/Windows/Fonts/ARIAL.TTF', 'C:/Windows/Fonts/ARIALBD.TTF'),
        # David font - good Hebrew support
        ('C:/Windows/Fonts/David.ttf', 'C:/Windows/Fonts/Davidbd.ttf'),
        ('C:/Windows/Fonts/DAVID.TTF', 'C:/Windows/Fonts/DAVIDBD.TTF'),
        # Tahoma - also supports Hebrew
        ('C:/Windows/Fonts/tahoma.ttf', 'C:/Windows/Fonts/tahomabd.ttf'),
        # Linux fonts
        ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
        ('/usr/share/fonts/truetype/freefont/FreeSans.ttf', '/usr/share/fonts/truetype/freefont/FreeSansBold.ttf'),
        # NotoSans Hebrew
        ('/usr/share/fonts/truetype/noto/NotoSansHebrew-Regular.ttf', '/usr/share/fonts/truetype/noto/NotoSansHebrew-Bold.ttf'),
    ]

    for regular_path, bold_path in font_paths:
        if os.path.exists(regular_path):
            try:
                pdfmetrics.registerFont(TTFont('Hebrew', regular_path))
                if os.path.exists(bold_path):
                    pdfmetrics.registerFont(TTFont('Hebrew-Bold', bold_path))
                else:
                    pdfmetrics.registerFont(TTFont('Hebrew-Bold', regular_path))
                print(f"[OK] Successfully registered Hebrew font: {regular_path}")
                return True
            except Exception as e:
                print(f"[ERROR] Error registering font {regular_path}: {e}")
                continue

    print("[WARNING] No Hebrew font found. PDF will use default font - Hebrew text may not display correctly.")
    return False

# Register fonts on module load
HEBREW_FONT_AVAILABLE = register_hebrew_font()
FONT_NAME = 'Hebrew' if HEBREW_FONT_AVAILABLE else 'Helvetica'
FONT_NAME_BOLD = 'Hebrew-Bold' if HEBREW_FONT_AVAILABLE else 'Helvetica-Bold'

def safe_get(data, key, default=''):
    """Safely get a value from dictionary, handling None values"""
    value = data.get(key)
    if value is None or value == 'None' or value == '':
        return default
    return value

def generate_quote_pdf(quote_data, company_info=None):
    """
    Generate a professional PDF quote

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

        # Custom styles - Professional sizing
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
            fontName=FONT_NAME_BOLD
        )

        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=9,
            spaceAfter=4,
            fontName=FONT_NAME
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
        company_name = 'Solar Energy Solutions'
        if company_info and company_info.get('company_name'):
            company_name = company_info['company_name']

        # Add company logo if exists
        if company_info and company_info.get('company_logo'):
            logo_path = company_info['company_logo']
            # Remove leading slash if present
            if logo_path.startswith('/'):
                logo_path = logo_path[1:]

            # Check if logo file exists
            if os.path.exists(logo_path):
                try:
                    logo = Image(logo_path, width=2.5*inch, height=1*inch, kind='proportional')
                    logo.hAlign = 'CENTER'
                    elements.append(logo)
                    elements.append(Spacer(1, 0.2*inch))
                except Exception as e:
                    print(f"[ERROR] Error loading logo: {e}")

        # Title
        title = Paragraph(f"<para align=center><b>{company_name}</b></para>", title_style)
        elements.append(title)

        subtitle_text = f"<para align=center>{reshape_hebrew('הצעת מחיר אנרגיה סולארית')}</para>"
        subtitle = Paragraph(subtitle_text, subtitle_style)
        elements.append(subtitle)
        elements.append(Spacer(1, 0.15*inch))

        # Quote number and date
        today = datetime.now()
        valid_until = today + timedelta(days=30)

        quote_info = [
            [reshape_hebrew('מספר הצעה:'), str(safe_get(quote_data, 'quote_number', 'N/A'))],
            [reshape_hebrew('תאריך:'), today.strftime('%d/%m/%Y')],
            [reshape_hebrew('בתוקף עד:'), valid_until.strftime('%d/%m/%Y')]
        ]

        quote_table = Table(quote_info, colWidths=[1.5*inch, 2.5*inch])
        quote_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), FONT_NAME_BOLD),
            ('FONTNAME', (1, 0), (1, -1), FONT_NAME),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#4a5568')),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        elements.append(quote_table)
        elements.append(Spacer(1, 0.15*inch))

        # Customer Information
        customer_heading = Paragraph(reshape_hebrew("פרטי לקוח"), heading_style)
        elements.append(customer_heading)

        customer_name_val = safe_get(quote_data, 'customer_name', 'לא צוין')
        customer_phone_val = safe_get(quote_data, 'customer_phone', 'לא צוין')
        customer_email_val = safe_get(quote_data, 'customer_email', 'לא צוין')
        customer_address_val = safe_get(quote_data, 'customer_address', 'לא צוין')

        customer_data = [
            [reshape_hebrew('שם:'), customer_name_val],
            [reshape_hebrew('טלפון:'), customer_phone_val if customer_phone_val != 'לא צוין' else reshape_hebrew('לא צוין')],
            [reshape_hebrew('אימייל:'), customer_email_val if customer_email_val != 'לא צוין' else reshape_hebrew('לא צוין')],
            [reshape_hebrew('כתובת:'), customer_address_val if customer_address_val != 'לא צוין' else reshape_hebrew('לא צוין')],
        ]

        customer_table = Table(customer_data, colWidths=[1.2*inch, 4.8*inch])
        customer_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), FONT_NAME_BOLD),
            ('FONTNAME', (1, 0), (1, -1), FONT_NAME),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#4a5568')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        elements.append(customer_table)
        elements.append(Spacer(1, 0.15*inch))

        # System Specifications
        specs_heading = Paragraph(reshape_hebrew("מפרט מערכת"), heading_style)
        elements.append(specs_heading)

        system_size = quote_data.get('system_size', 0) or 0
        roof_area = quote_data.get('roof_area')
        annual_prod = quote_data.get('annual_production', 0) or 0

        def format_spec_value(value, suffix='', default='לא צוין'):
            if value is None or value == '' or value == 'None' or value == 0:
                return reshape_hebrew(default)
            return reshape_hebrew(f"{value}{suffix}")

        specs_data = [
            [reshape_hebrew('גודל מערכת:'), reshape_hebrew(f"{system_size} קוט״ש")],
            [reshape_hebrew('שטח גג:'), format_spec_value(roof_area, ' מ״ר')],
            [reshape_hebrew('ייצור שנתי:'), reshape_hebrew(f"{int(annual_prod):,} קוט״ש/שנה") if annual_prod else reshape_hebrew('לא צוין')],
            [reshape_hebrew('סוג פאנל:'), format_spec_value(safe_get(quote_data, 'panel_type'))],
            [reshape_hebrew('מספר פאנלים:'), format_spec_value(safe_get(quote_data, 'panel_count'))],
            [reshape_hebrew('סוג ממיר:'), format_spec_value(safe_get(quote_data, 'inverter_type'))],
            [reshape_hebrew('כיוון:'), format_spec_value(safe_get(quote_data, 'direction'))],
            [reshape_hebrew('זווית הטיה:'), format_spec_value(quote_data.get('tilt_angle'), '°')],
            [reshape_hebrew('אחריות:'), reshape_hebrew(f"{quote_data.get('warranty_years', 25)} שנים")],
        ]

        specs_table = Table(specs_data, colWidths=[2*inch, 4*inch])
        specs_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), FONT_NAME_BOLD),
            ('FONTNAME', (1, 0), (1, -1), FONT_NAME),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#4a5568')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f7fafc')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(specs_table)
        elements.append(Spacer(1, 0.15*inch))

        # Get financial data for charts
        total_price = quote_data.get('total_price', 0) or 0
        annual_revenue = quote_data.get('annual_revenue', 0) or 0

        # Production Charts
        if system_size and annual_prod:
            # Monthly Production Chart
            chart_heading = Paragraph(reshape_hebrew("ייצור אנרגיה חודשי"), heading_style)
            elements.append(chart_heading)

            try:
                monthly_chart_bytes = generate_monthly_production_chart(system_size, annual_prod)
                monthly_chart_img = Image(BytesIO(monthly_chart_bytes), width=6.5*inch, height=2.4*inch)
                elements.append(monthly_chart_img)
                elements.append(Spacer(1, 0.15*inch))
            except Exception as e:
                print(f"[ERROR] Error generating monthly chart: {e}")
                traceback.print_exc()

            # Payback Period Chart
            if total_price and annual_revenue:
                payback_heading = Paragraph(reshape_hebrew("ניתוח החזר השקעה"), heading_style)
                elements.append(payback_heading)

                try:
                    payback_chart_bytes = generate_payback_chart(total_price, annual_revenue)
                    payback_chart_img = Image(BytesIO(payback_chart_bytes), width=6.5*inch, height=2.6*inch)
                    elements.append(payback_chart_img)
                    elements.append(Spacer(1, 0.15*inch))
                except Exception as e:
                    print(f"[ERROR] Error generating payback chart: {e}")
                    traceback.print_exc()

        # Financial Summary
        financial_heading = Paragraph(reshape_hebrew("סיכום פיננסי"), heading_style)
        elements.append(financial_heading)

        payback = quote_data.get('payback_period', 0) or 0

        financial_data = [
            [reshape_hebrew('תיאור'), reshape_hebrew('סכום')],
            [reshape_hebrew('סך ההשקעה'), f"₪{int(total_price):,}"],
            [reshape_hebrew('הכנסה שנתית משוערת'), f"₪{int(annual_revenue):,}"],
            [reshape_hebrew('תקופת החזר'), reshape_hebrew(f"{payback} שנים")],
            [reshape_hebrew('חיסכון כולל ל-25 שנה'), f"₪{int(annual_revenue * 25):,}"],
        ]

        financial_table = Table(financial_data, colWidths=[3.5*inch, 2.5*inch])
        financial_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#00358A')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), FONT_NAME_BOLD),
            ('FONTNAME', (0, 1), (0, -1), FONT_NAME),
            ('FONTNAME', (1, 1), (1, -1), FONT_NAME_BOLD),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.75, colors.HexColor('#e2e8f0')),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f7fafc')),
            ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#f7fafc')),
        ]))
        elements.append(financial_table)
        elements.append(Spacer(1, 0.15*inch))

        # Environmental Impact
        env_heading = Paragraph(reshape_hebrew("השפעה סביבתית"), heading_style)
        elements.append(env_heading)

        trees = int(annual_prod * 0.05) if annual_prod else 0
        co2_saved = int(annual_prod * 0.5) if annual_prod else 0

        env_text = reshape_hebrew(f"המערכת הסולארית שלך תייצר כ-{int(annual_prod):,} קוט״ש של אנרגיה נקייה בשנה, "
                    f"שווה ערך לנטיעת {trees:,} עצים והפחתת פליטות CO2 ב-{co2_saved:,} ק״ג בשנה. "
                    f"במשך 25 שנה, זהו תרומה משמעותית לקיימות סביבתית.")

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

        footer_lines = [f"<b>{company_name}</b>"]

        if company_info:
            if company_info.get('company_phone'):
                footer_lines.append(f"{company_info['company_phone']}")
            if company_info.get('company_email'):
                footer_lines.append(f"{company_info['company_email']}")
            if company_info.get('company_address'):
                footer_lines.append(f"{company_info['company_address']}")

        footer_lines.append("")
        footer_lines.append(f"<i>{reshape_hebrew('הצעה זו בתוקף 30 ימים מתאריך ההנפקה.')}</i>")
        footer_lines.append(reshape_hebrew("תודה שבחרתם באנרגיה סולארית!"))

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
