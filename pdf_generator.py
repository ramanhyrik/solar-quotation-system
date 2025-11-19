from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from io import BytesIO
from datetime import datetime, timedelta
from chart_generator import generate_monthly_production_chart, generate_payback_chart
import os

def generate_quote_pdf(quote_data, company_info=None):
    """
    Generate a professional PDF quote

    Args:
        quote_data: Dictionary containing quote information
        company_info: Dictionary containing company information

    Returns:
        BytesIO object containing the PDF
    """

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
        fontName='Helvetica-Bold'
    )

    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=11,
        textColor=colors.HexColor('#667eea'),
        spaceAfter=8,
        spaceBefore=12,
        fontName='Helvetica-Bold'
    )

    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=9,
        spaceAfter=4
    )

    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=12,
        textColor=colors.HexColor('#667eea'),
        spaceAfter=4,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )

    # Company header
    company_name = 'Solar Energy Solutions'
    if company_info and 'company_name' in company_info:
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
                print(f"Error loading logo: {e}")

    # Title
    title = Paragraph(f"<para align=center><b>{company_name}</b></para>", title_style)
    elements.append(title)

    subtitle_text = "<para align=center>הצעת מחיר אנרגיה סולארית</para>"
    subtitle = Paragraph(subtitle_text, subtitle_style)
    elements.append(subtitle)
    elements.append(Spacer(1, 0.15*inch))

    # Quote number and date
    today = datetime.now()
    valid_until = today + timedelta(days=30)

    quote_info = [
        ['מספר הצעה:', str(quote_data.get('quote_number', 'N/A'))],
        ['תאריך:', today.strftime('%d/%m/%Y')],
        ['בתוקף עד:', valid_until.strftime('%d/%m/%Y')]
    ]

    quote_table = Table(quote_info, colWidths=[1.5*inch, 2.5*inch])
    quote_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#4a5568')),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(quote_table)
    elements.append(Spacer(1, 0.15*inch))

    # Customer Information
    customer_heading = Paragraph("פרטי לקוח", heading_style)
    elements.append(customer_heading)

    customer_data = [
        ['שם:', str(quote_data.get('customer_name', 'N/A'))],
        ['טלפון:', str(quote_data.get('customer_phone', 'N/A'))],
        ['אימייל:', str(quote_data.get('customer_email', 'N/A'))],
        ['כתובת:', str(quote_data.get('customer_address', 'N/A'))],
    ]

    customer_table = Table(customer_data, colWidths=[1.2*inch, 4.8*inch])
    customer_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#4a5568')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(customer_table)
    elements.append(Spacer(1, 0.15*inch))

    # System Specifications
    specs_heading = Paragraph("מפרט מערכת", heading_style)
    elements.append(specs_heading)

    system_size = quote_data.get('system_size', 0)
    roof_area = quote_data.get('roof_area')
    annual_prod = quote_data.get('annual_production', 0)

    specs_data = [
        ['גודל מערכת:', f"{system_size} קוט״ש"],
        ['שטח גג:', f"{roof_area} מ״ר" if roof_area else 'לא צוין'],
        ['ייצור שנתי:', f"{int(annual_prod):,} קוט״ש/שנה" if annual_prod else 'לא צוין'],
        ['סוג פאנל:', str(quote_data.get('panel_type', 'לא צוין'))],
        ['מספר פאנלים:', str(quote_data.get('panel_count', 'לא צוין'))],
        ['סוג ממיר:', str(quote_data.get('inverter_type', 'לא צוין'))],
        ['כיוון:', str(quote_data.get('direction', 'לא צוין')).title()],
        ['זווית הטיה:', f"{quote_data.get('tilt_angle', 'לא צוין')}°" if quote_data.get('tilt_angle') else 'לא צוין'],
        ['אחריות:', f"{quote_data.get('warranty_years', 25)} שנים"],
    ]

    specs_table = Table(specs_data, colWidths=[2*inch, 4*inch])
    specs_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
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
    total_price = quote_data.get('total_price', 0)
    annual_revenue = quote_data.get('annual_revenue', 0)

    # Production Charts
    if system_size and annual_prod:
        # Monthly Production Chart
        chart_heading = Paragraph("ייצור אנרגיה חודשי", heading_style)
        elements.append(chart_heading)

        try:
            monthly_chart_bytes = generate_monthly_production_chart(system_size, annual_prod)
            monthly_chart_img = Image(BytesIO(monthly_chart_bytes), width=6.5*inch, height=2.4*inch)
            elements.append(monthly_chart_img)
            elements.append(Spacer(1, 0.15*inch))
        except Exception as e:
            print(f"Error generating monthly chart: {e}")

        # Payback Period Chart
        if total_price and annual_revenue:
            payback_heading = Paragraph("ניתוח החזר השקעה", heading_style)
            elements.append(payback_heading)

            try:
                payback_chart_bytes = generate_payback_chart(total_price, annual_revenue)
                payback_chart_img = Image(BytesIO(payback_chart_bytes), width=6.5*inch, height=2.6*inch)
                elements.append(payback_chart_img)
                elements.append(Spacer(1, 0.15*inch))
            except Exception as e:
                print(f"Error generating payback chart: {e}")

    # Financial Summary
    financial_heading = Paragraph("סיכום פיננסי", heading_style)
    elements.append(financial_heading)

    payback = quote_data.get('payback_period', 0)

    financial_data = [
        ['תיאור', 'סכום'],
        ['סך ההשקעה', f"₪{int(total_price):,}"],
        ['הכנסה שנתית משוערת', f"₪{int(annual_revenue):,}"],
        ['תקופת החזר', f"{payback} שנים"],
        ['חיסכון כולל ל-25 שנה', f"₪{int(annual_revenue * 25):,}"],
    ]

    financial_table = Table(financial_data, colWidths=[3.5*inch, 2.5*inch])
    financial_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica'),
        ('FONTNAME', (1, 1), (1, -1), 'Helvetica-Bold'),
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
    env_heading = Paragraph("השפעה סביבתית", heading_style)
    elements.append(env_heading)

    trees = int(annual_prod * 0.05) if annual_prod else 0
    co2_saved = int(annual_prod * 0.5) if annual_prod else 0

    env_text = f"המערכת הסולארית שלך תייצר כ-<b>{int(annual_prod):,} קוט״ש</b> של אנרגיה נקייה בשנה, " \
                f"שווה ערך לנטיעת <b>{trees:,} עצים</b> והפחתת פליטות CO2 ב-<b>{co2_saved:,} ק״ג בשנה</b>. " \
                f"במשך 25 שנה, זהו תרומה משמעותית לקיימות סביבתית."

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
        leading=10
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
    footer_lines.append("<i>הצעה זו בתוקף 30 ימים מתאריך ההנפקה.</i>")
    footer_lines.append("תודה שבחרתם באנרגיה סולארית!")

    footer_text = "<para align=center>" + "<br/>".join(footer_lines) + "</para>"
    footer = Paragraph(footer_text, footer_style)
    elements.append(footer)

    # Build PDF
    try:
        doc.build(elements)
        buffer.seek(0)
        return buffer
    except Exception as e:
        print(f"Error building PDF: {e}")
        raise
