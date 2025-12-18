let currentQuoteData = {};

async function calculateQuote() {
    const systemSize = parseFloat(document.getElementById('systemSize').value);

    if (!systemSize || systemSize <= 0) {
        alert('נא להזין גודל מערכת תקין');
        return;
    }

    try {
        const formData = new FormData();
        formData.append('system_size', systemSize);

        const response = await fetch('/api/calculate', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        // שמירה לשימוש מאוחר יותר
        currentQuoteData = {
            total_price: data.total_price,
            annual_revenue: data.annual_revenue,
            payback_period: data.payback_period,
            annual_production: data.annual_production
        };

        // עדכון ממשק
        document.getElementById('totalPrice').textContent = `₪${data.total_price.toLocaleString()}`;
        document.getElementById('annualRevenue').textContent = `₪${data.annual_revenue.toLocaleString()}`;
        document.getElementById('paybackPeriod').textContent = `${data.payback_period} שנים`;

        document.getElementById('calculations').style.display = 'grid';

    } catch (error) {
        console.error('Error:', error);
        alert('שגיאה בחישוב הצעה');
    }
}

async function saveQuote() {
    const customerName = document.getElementById('customerName').value;
    const systemSize = parseFloat(document.getElementById('systemSize').value);

    if (!customerName || !systemSize) {
        alert('נא למלא שדות חובה (שם לקוח וגודל מערכת)');
        return;
    }

    if (!currentQuoteData.total_price) {
        alert('נא לחשב את ההצעה קודם');
        return;
    }

    const quoteData = {
        customer_name: customerName,
        customer_phone: document.getElementById('customerPhone').value,
        customer_email: document.getElementById('customerEmail').value,
        customer_address: document.getElementById('customerAddress').value,
        system_size: systemSize,
        roof_area: parseFloat(document.getElementById('roofArea').value) || null,
        annual_production: currentQuoteData.annual_production,
        panel_type: document.getElementById('panelType').value,
        panel_count: parseInt(document.getElementById('panelCount').value) || null,
        inverter_type: document.getElementById('inverterType').value,
        direction: document.getElementById('direction').value,
        tilt_angle: parseFloat(document.getElementById('tiltAngle').value) || null,
        warranty_years: parseInt(document.getElementById('warrantyYears').value) || 25,
        total_price: currentQuoteData.total_price,
        annual_revenue: currentQuoteData.annual_revenue,
        payback_period: currentQuoteData.payback_period,
        model_type: window.currentModel || 'purchase'
    };

    try {
        const response = await fetch('/api/quotes', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(quoteData)
        });

        if (response.ok) {
            alert('ההצעה נשמרה בהצלחה!');
            // ניקוי טופס
            document.querySelectorAll('input').forEach(input => input.value = '');
            document.getElementById('calculations').style.display = 'none';
            currentQuoteData = {};
        } else {
            alert('שגיאה בשמירת הצעה');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('שגיאה בשמירת הצעה');
    }
}

async function loadQuoteHistory() {
    try {
        const response = await fetch('/api/quotes');
        const data = await response.json();

        const tbody = document.querySelector('#quotesTable tbody');
        tbody.innerHTML = '';

        data.quotes.forEach(quote => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td><strong style="color: #00358A; font-size: 16px;">${quote.id}</strong></td>
                <td>${quote.quote_number}</td>
                <td>${quote.customer_name}</td>
                <td>${quote.system_size} קוט״ש</td>
                <td>₪${quote.total_price.toLocaleString()}</td>
                <td>${new Date(quote.created_at).toLocaleDateString('he-IL')}</td>
                <td>
                    <div style="display: flex; gap: 8px; justify-content: flex-end; flex-wrap: wrap;">
                        <button onclick="generateSignatureLink(${quote.id})" style="background: #28a745; color: white; padding: 8px 12px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; white-space: nowrap;">✍️ קישור חתימה</button>
                        <button onclick="viewQuoteAnalysis(${quote.id})" style="background: #D9FF0D; color: #00358A; padding: 8px 12px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; white-space: nowrap;">ניתוח פיננסי</button>
                        <button onclick="downloadPDF(${quote.id})" style="background: #00358A; color: white; padding: 8px 12px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; white-space: nowrap;">PDF</button>
                        <button onclick="deleteQuote(${quote.id})" style="background: #dc2626; color: white; padding: 8px 12px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; white-space: nowrap;">מחק</button>
                    </div>
                </td>
            `;
            tbody.appendChild(row);
        });

    } catch (error) {
        console.error('Error:', error);
        alert('שגיאה בטעינת היסטוריית הצעות');
    }
}

async function deleteQuote(id) {
    if (!confirm('האם אתה בטוח שברצונך למחוק הצעה זו?')) {
        return;
    }

    try {
        const response = await fetch(`/api/quotes/${id}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            loadQuoteHistory();
        } else {
            alert('שגיאה במחיקת הצעה');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('שגיאה במחיקת הצעה');
    }
}

function downloadPDF(quoteId) {
    window.location.href = `/api/quotes/${quoteId}/pdf`;
}

async function generateSignatureLink(quoteId) {
    try {
        const response = await fetch(`/api/quotes/${quoteId}/generate-signature-link`, {
            method: 'POST'
        });

        if (!response.ok) {
            throw new Error('Failed to generate signature link');
        }

        const data = await response.json();

        // Create a nice modal/alert with the link
        const modal = document.createElement('div');
        modal.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; z-index: 10000;';

        modal.innerHTML = `
            <div style="background: white; padding: 30px; border-radius: 12px; max-width: 600px; width: 90%; direction: rtl;">
                <h2 style="color: #00358A; margin-bottom: 20px;">✅ קישור חתימה נוצר בהצלחה!</h2>

                <div style="background: #f7fafc; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                    <strong style="display: block; margin-bottom: 10px; color: #2d3748;">פרטי הצעה:</strong>
                    <div style="font-size: 14px; color: #4a5568; line-height: 1.8;">
                        מספר הצעה: <strong>${data.quote_number}</strong><br>
                        לקוח: <strong>${data.customer_name}</strong><br>
                        אימייל: <strong>${data.customer_email || 'לא צוין'}</strong>
                    </div>
                </div>

                <div style="background: #e8f4f8; padding: 15px; border-radius: 8px; margin-bottom: 20px; border-right: 4px solid #00358A;">
                    <strong style="display: block; margin-bottom: 10px; color: #00358A;">קישור לחתימה:</strong>
                    <input type="text" value="${data.full_url}" readonly
                           style="width: 100%; padding: 10px; border: 2px solid #00358A; border-radius: 6px; font-size: 13px; font-family: monospace;"
                           id="signatureLinkInput">
                </div>

                <div style="display: flex; gap: 10px;">
                    <button onclick="copySignatureLink()"
                            style="flex: 1; padding: 12px; background: #28a745; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 600;">
                        📋 העתק קישור
                    </button>
                    <button onclick="closeSignatureModal()"
                            style="flex: 1; padding: 12px; background: #6c757d; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 600;">
                        סגור
                    </button>
                </div>

                <div style="margin-top: 15px; padding: 12px; background: #fff3cd; border-radius: 6px; font-size: 13px; color: #856404;">
                    ⏰ הקישור תקף ל-30 יום
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        // Store the modal reference for closing
        window.currentSignatureModal = modal;

        // Auto-select the link text
        setTimeout(() => {
            document.getElementById('signatureLinkInput').select();
        }, 100);

    } catch (error) {
        console.error('Error:', error);
        alert('שגיאה ביצירת קישור חתימה');
    }
}

function copySignatureLink() {
    const input = document.getElementById('signatureLinkInput');
    input.select();
    document.execCommand('copy');

    // Show success message
    const btn = event.target;
    const originalText = btn.textContent;
    btn.textContent = '✅ הועתק!';
    btn.style.background = '#00358A';

    setTimeout(() => {
        btn.textContent = originalText;
        btn.style.background = '#28a745';
    }, 2000);
}

function closeSignatureModal() {
    if (window.currentSignatureModal) {
        window.currentSignatureModal.remove();
        window.currentSignatureModal = null;
    }
}

async function viewQuoteAnalysis(quoteId) {
    try {
        // Fetch the specific quote data
        const response = await fetch(`/api/quotes/${quoteId}`);
        if (!response.ok) {
            throw new Error('Failed to fetch quote');
        }

        const quote = await response.json();

        // Call the financial comparison function from dashboard.html
        if (typeof calculateFinancialComparison === 'function') {
            await calculateFinancialComparison(quote.system_size, quote.total_price);
            // Switch to comparison section (defined in dashboard.html)
            if (typeof showSection === 'function') {
                showSection('comparison');
            }
        } else {
            alert('פונקציית הניתוח הפיננסי לא זמינה');
        }

    } catch (error) {
        console.error('Error:', error);
        alert('שגיאה בטעינת ניתוח פיננסי');
    }
}

async function generatePDF() {
    const customerName = document.getElementById('customerName').value;
    const systemSize = parseFloat(document.getElementById('systemSize').value);

    if (!customerName || !systemSize) {
        alert('נא למלא שדות חובה (שם לקוח וגודל מערכת) ולחשב קודם');
        return;
    }

    if (!currentQuoteData.total_price) {
        alert('נא לחשב את ההצעה קודם');
        return;
    }

    // קודם, שמור את ההצעה
    const quoteData = {
        customer_name: customerName,
        customer_phone: document.getElementById('customerPhone').value,
        customer_email: document.getElementById('customerEmail').value,
        customer_address: document.getElementById('customerAddress').value,
        system_size: systemSize,
        roof_area: parseFloat(document.getElementById('roofArea').value) || null,
        annual_production: currentQuoteData.annual_production,
        panel_type: document.getElementById('panelType').value,
        panel_count: parseInt(document.getElementById('panelCount').value) || null,
        inverter_type: document.getElementById('inverterType').value,
        direction: document.getElementById('direction').value,
        tilt_angle: parseFloat(document.getElementById('tiltAngle').value) || null,
        warranty_years: parseInt(document.getElementById('warrantyYears').value) || 25,
        total_price: currentQuoteData.total_price,
        annual_revenue: currentQuoteData.annual_revenue,
        payback_period: currentQuoteData.payback_period,
        model_type: window.currentModel || 'purchase'
    };

    try {
        // שמירת הצעה קודם
        const response = await fetch('/api/quotes', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(quoteData)
        });

        if (!response.ok) {
            throw new Error('נכשל בשמירת הצעה');
        }

        const result = await response.json();
        const quoteId = result.quote_id;

        // יצירת והורדת PDF
        window.location.href = `/api/quotes/${quoteId}/pdf`;

        alert('ה-PDF נוצר ומוריד!');

    } catch (error) {
        console.error('Error:', error);
        alert('שגיאה ביצירת PDF. נסה שוב.');
    }
}
